package com.gradedreader.korean.learning

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.gradedreader.korean.data.DictionaryEntryEntity
import com.gradedreader.korean.data.EventBatchRequest
import com.gradedreader.korean.data.LearnerWordStateEntity
import com.gradedreader.korean.data.LearningEventDto
import com.gradedreader.korean.data.LocalDatabase
import com.gradedreader.korean.data.LocalDatabaseFactory
import com.gradedreader.korean.data.ReaderApi
import com.gradedreader.korean.data.ReaderApiFactory
import com.gradedreader.korean.data.SessionRepository
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

class EventSyncWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val database = LocalDatabaseFactory.create(applicationContext)
        var attemptedEventIds = emptyList<String>()
        try {
            val session = SessionRepository.create(applicationContext)
            if (session.accessToken().isNullOrBlank()) return Result.success()

            val json = Json { ignoreUnknownKeys = true }
            val api = ReaderApiFactory.create(session)
            while (true) {
                val events = database.readerDao().pendingEvents(BATCH_SIZE)
                if (events.isEmpty()) return Result.success()

                attemptedEventIds = events.map { it.id }
                val decodedEvents = events.map { json.decodeFromString<LearningEventDto>(it.payload) }
                val result = api.syncEvents(EventBatchRequest(decodedEvents))
                if (result.accepted + result.duplicates != events.size) {
                    database.readerDao().incrementAttempts(attemptedEventIds)
                    return Result.retry()
                }

                reconcileLearnerData(database, api, decodedEvents, json)
                database.readerDao().removeEvents(attemptedEventIds)
                attemptedEventIds = emptyList()
            }
        } catch (error: CancellationException) {
            throw error
        } catch (_: Exception) {
            if (attemptedEventIds.isNotEmpty()) database.readerDao().incrementAttempts(attemptedEventIds)
            return Result.retry()
        } finally {
            database.close()
        }
    }

    private suspend fun reconcileLearnerData(
        database: LocalDatabase,
        api: ReaderApi,
        events: List<LearningEventDto>,
        json: Json,
    ) {
        val state = api.learnerState().map { value ->
            LearnerWordStateEntity(value.lemma, value.confidence, value.encounters, value.lookups, value.correctAnswers, value.incorrectAnswers)
        }
        database.readerDao().replaceLearnerWordStates(state)
        events.flatMap { event -> listOfNotNull(event.lemma) + event.targetLemmas }
            .distinct()
            .forEach { lemma ->
                try {
                    val entry = api.dictionary(lemma)
                    database.readerDao().saveDictionary(DictionaryEntryEntity(entry.lemma, entry.gloss, entry.englishTranslation, entry.partOfSpeech, json.encodeToString(entry.forms), entry.source))
                } catch (error: CancellationException) {
                    throw error
                } catch (_: Exception) {
                }
            }
    }

    private companion object {
        const val BATCH_SIZE = 100
    }
}
