package com.gradedreader.korean.data

import android.content.Context
import com.gradedreader.korean.BuildConfig
import com.gradedreader.korean.learning.EventSyncScheduler
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Response
import okhttp3.Authenticator
import okhttp3.Route
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.time.Instant
import java.util.UUID
import java.util.concurrent.TimeUnit

fun interface AccessTokenProvider { fun accessToken(): String? }

class AuthInterceptor(private val tokenProvider: AccessTokenProvider) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val token = tokenProvider.accessToken()
        val request = chain.request().newBuilder().apply {
            if (!token.isNullOrBlank()) header("Authorization", "Bearer $token")
        }.build()
        return chain.proceed(request)
    }
}

object ReaderApiFactory {
    fun create(tokenProvider: AccessTokenProvider = AccessTokenProvider { null }): ReaderApi {
        val json = Json { ignoreUnknownKeys = true }
        val logging = HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC }
        val authApi = authApi()
        val client = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(60, TimeUnit.SECONDS)
            .callTimeout(60, TimeUnit.SECONDS)
            .addInterceptor(AuthInterceptor(tokenProvider))
            .authenticator(TokenRefreshAuthenticator(tokenProvider, authApi))
            .addInterceptor(logging)
            .build()
        return Retrofit.Builder()
            .baseUrl(BuildConfig.BACKEND_BASE_URL.ensureTrailingSlash())
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(ReaderApi::class.java)
    }

    fun authApi(): AuthApi {
        val json = Json { ignoreUnknownKeys = true }
        return Retrofit.Builder()
            .baseUrl(BuildConfig.BACKEND_BASE_URL.ensureTrailingSlash())
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(AuthApi::class.java)
    }

    private fun String.ensureTrailingSlash() = if (endsWith('/')) this else "$this/"
}

private class TokenRefreshAuthenticator(private val tokenProvider: AccessTokenProvider, private val authApi: AuthApi) : Authenticator {
    override fun authenticate(route: Route?, response: Response): okhttp3.Request? {
        if (responseCount(response) >= 2 || tokenProvider !is SessionRepository || response.request.header("Authorization") == null) return null
        if (!tokenProvider.refresh(authApi)) return null
        return response.request.newBuilder().header("Authorization", "Bearer ${tokenProvider.accessToken()}").build()
    }

    private fun responseCount(response: Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) { count += 1; prior = prior.priorResponse }
        return count
    }
}

class ReaderRepository private constructor(private val context: Context, private val dao: ReaderDao, private val api: ReaderApi) {
    val savedReadings: Flow<List<ReadingEntity>> = dao.readings()

    fun savedReading(readingId: String): Flow<GeneratedReading?> = dao.readingContent(readingId).map { entity ->
        entity?.let { json.decodeFromString(GeneratedReading.serializer(), it.content) }
    }

    suspend fun generate(request: GenerationRequest): GeneratedReading {
        val reading = api.generate(request)
        save(reading, request)
        cacheDictionaryEntries(reading)
        return reading
    }

    suspend fun recordReadingOpened(reading: GeneratedReading) {
        enqueueEvent(LearningEventDto(UUID.randomUUID().toString(), "reading_opened", Instant.now().toString(), readingId = reading.id))
        reading.tokens.forEach { token ->
            enqueueEvent(LearningEventDto(UUID.randomUUID().toString(), "encounter", Instant.now().toString(), readingId = reading.id, sentenceId = token.sentenceId, lemma = token.lemma))
        }
    }

    suspend fun recordQuestionAnswer(reading: GeneratedReading, question: GeneratedQuestion, optionId: String, lookupBeforeAnswer: Boolean) {
        enqueueEvent(LearningEventDto(UUID.randomUUID().toString(), "question_answer", Instant.now().toString(), readingId = reading.id, targetLemmas = question.targetLemmas, correct = optionId == question.correctOptionId, lookupBeforeAnswer = lookupBeforeAnswer))
    }
    suspend fun lookup(readingId: String, token: GeneratedToken): DictionaryEntryEntity {
        val entry = try {
            api.dictionary(token.lemma).also { response ->
                dao.saveDictionary(DictionaryEntryEntity(response.lemma, response.gloss, response.englishTranslation, response.partOfSpeech, json.encodeToString(response.forms), response.source))
                dao.saveLearnerWordState(dao.learnerWordState(response.lemma) ?: LearnerWordStateEntity(response.lemma, encounters = response.encounters, lookups = response.lookups))
            }.let { response -> dao.dictionary(response.lemma)!! }
        } catch (error: Exception) {
            dao.dictionary(token.lemma) ?: throw error
        }
        dao.recordLookup(entry.lemma)
        enqueueEvent(LearningEventDto(UUID.randomUUID().toString(), "lookup", Instant.now().toString(), readingId = readingId, lemma = entry.lemma, provider = "local"))
        return entry
    }

    suspend fun annotation(readingId: String, tokenId: String): AnnotationEntity? = dao.annotation(readingId, tokenId)

    suspend fun saveAnnotation(readingId: String, tokenId: String, note: String) {
        val timestamp = System.currentTimeMillis()
        dao.saveAnnotation(AnnotationEntity(readingId, tokenId, note.trim(), timestamp))
        try {
            val saved = api.saveAnnotation(readingId, tokenId, AnnotationInputDto(note.trim()))
            dao.saveAnnotation(AnnotationEntity(saved.readingId, saved.tokenId, saved.note, Instant.parse(saved.updatedAt).toEpochMilli()))
        } catch (_: Exception) {
        }
    }

    private suspend fun enqueueEvent(event: LearningEventDto) {
        dao.enqueue(PendingEventEntity(event.id, event.type, json.encodeToString(event), System.currentTimeMillis()))
        EventSyncScheduler.schedule(context)
    }
    private suspend fun save(reading: GeneratedReading, request: GenerationRequest) {
        dao.saveReading(
            ReadingEntity(
                id = reading.id,
                title = reading.title,
                text = reading.text,
                genre = request.genre,
                length = request.length,
                newWordIntensity = request.newWordIntensity,
                grammarIntensity = request.grammarIntensity,
            ),
        )
        dao.saveReadingContent(ReadingContentEntity(reading.id, json.encodeToString(GeneratedReading.serializer(), reading)))
    }

    private suspend fun cacheDictionaryEntries(reading: GeneratedReading) {
        reading.tokens
            .asSequence()
            .map(GeneratedToken::lemma)
            .map(String::trim)
            .filter(String::isNotEmpty)
            .distinct()
            .toList()
            .chunked(CACHE_BATCH_SIZE)
            .forEach { lemmas ->
                coroutineScope {
                    lemmas.map { lemma -> async { cacheDictionaryEntry(lemma) } }.awaitAll()
                }
            }
    }

    private suspend fun cacheDictionaryEntry(lemma: String) {
        if (dao.dictionary(lemma) != null) return
        try {
            val response = api.dictionary(lemma)
            dao.saveDictionary(DictionaryEntryEntity(response.lemma, response.gloss, response.englishTranslation, response.partOfSpeech, json.encodeToString(response.forms), response.source))
            dao.saveLearnerWordState(dao.learnerWordState(response.lemma) ?: LearnerWordStateEntity(response.lemma, encounters = response.encounters, lookups = response.lookups))
        } catch (error: Exception) {
            if (error is CancellationException) throw error
        }
    }

    companion object {
        private const val CACHE_BATCH_SIZE = 4
        private val json = Json { ignoreUnknownKeys = true }
        fun create(context: Context, tokenProvider: AccessTokenProvider = AccessTokenProvider { null }): ReaderRepository {
            EventSyncScheduler.schedule(context)
            val database = LocalDatabaseFactory.create(context)
            return ReaderRepository(context.applicationContext, database.readerDao(), ReaderApiFactory.create(tokenProvider))
        }
    }
}
