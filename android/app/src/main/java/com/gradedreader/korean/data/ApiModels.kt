package com.gradedreader.korean.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.PUT
import retrofit2.Call

@Serializable data class GenerationRequest(val genre: String, val length: String, @SerialName("new_word_intensity") val newWordIntensity: Int, @SerialName("grammar_intensity") val grammarIntensity: Int, val model: String? = null)
@Serializable data class GeneratedSentence(val id: String, val text: String)
@Serializable data class GeneratedToken(val id: String, val surface: String, val lemma: String, @SerialName("sentence_id") val sentenceId: String)
@Serializable data class GeneratedOption(val id: String, val text: String)
@Serializable data class GeneratedQuestion(val id: String, val prompt: String, val options: List<GeneratedOption>, @SerialName("correct_option_id") val correctOptionId: String, @SerialName("evidence_sentence_ids") val evidenceSentenceIds: List<String> = emptyList(), @SerialName("target_lemmas") val targetLemmas: List<String> = emptyList(), @SerialName("target_grammar") val targetGrammar: List<String> = emptyList(), val explanation: String, @SerialName("english_translation") val englishTranslation: String = "", @SerialName("english_explanation") val englishExplanation: String = "")
@Serializable data class GeneratedReading(val id: String, val title: String, val text: String, val sentences: List<GeneratedSentence> = emptyList(), val tokens: List<GeneratedToken> = emptyList(), @SerialName("target_lemmas") val targetLemmas: List<String> = emptyList(), @SerialName("target_grammar") val targetGrammar: List<String> = emptyList(), val questions: List<GeneratedQuestion>, val rationale: String = "", @SerialName("english_translation") val englishTranslation: String = "", @SerialName("english_title") val englishTitle: String = "")
@Serializable data class DictionaryEntryDto(val lemma: String, val gloss: String, @SerialName("english_translation") val englishTranslation: String? = null, @SerialName("part_of_speech") val partOfSpeech: String?, val forms: List<String>, val source: String, val encounters: Int, val lookups: Int)
@Serializable data class AnnotationInputDto(val note: String)
@Serializable data class AnnotationDto(val id: String, @SerialName("reading_id") val readingId: String, @SerialName("token_id") val tokenId: String, val note: String, @SerialName("updated_at") val updatedAt: String)
@Serializable data class LearningEventDto(val id: String, val type: String, @SerialName("occurred_at") val occurredAt: String, @SerialName("reading_id") val readingId: String? = null, @SerialName("sentence_id") val sentenceId: String? = null, val lemma: String? = null, val provider: String? = null, @SerialName("target_lemmas") val targetLemmas: List<String> = emptyList(), val correct: Boolean? = null, @SerialName("lookup_before_answer") val lookupBeforeAnswer: Boolean = false)
@Serializable data class EventBatchRequest(val events: List<LearningEventDto>)
@Serializable data class EventBatchResponse(val accepted: Int, val duplicates: Int)
@Serializable data class LearnerWordStateDto(val lemma: String, val confidence: Float, val encounters: Int, val lookups: Int, @SerialName("correct_answers") val correctAnswers: Int, @SerialName("incorrect_answers") val incorrectAnswers: Int)
@Serializable data class Credentials(val email: String, val password: String)
@Serializable data class TokenResponse(@SerialName("access_token") val accessToken: String, @SerialName("refresh_token") val refreshToken: String, @SerialName("token_type") val tokenType: String = "bearer")
@Serializable data class RefreshRequest(@SerialName("refresh_token") val refreshToken: String)
@Serializable data class VocabularyInputDto(val term: String, val meaning: String? = null, val tags: List<String> = emptyList())
@Serializable data class VocabularyDto(val id: String, val term: String, @SerialName("normalized_term") val normalizedTerm: String, val meaning: String? = null, val tags: List<String> = emptyList())
@Serializable data class ImportPreviewRequest(val content: String, val delimiter: String? = null)
@Serializable data class ImportPreviewResponse(val headers: List<String>, val rows: List<Map<String, String>>, @SerialName("column_values") val columnValues: Map<String, List<String>> = emptyMap())
@Serializable data class ImportRequest(val content: String, val delimiter: String, val filename: String, @SerialName("term_column") val termColumn: String, @SerialName("meaning_column") val meaningColumn: String? = null, @SerialName("tags_column") val tagsColumn: String? = null, @SerialName("note_type_column") val noteTypeColumn: String? = null, @SerialName("note_type") val noteType: String? = null)
@Serializable data class ImportResponse(val imported: Int, val updated: Int, val skipped: Int)

interface AuthApi {
    @POST("auth/register") suspend fun register(@Body request: Credentials): TokenResponse
    @POST("auth/login") suspend fun login(@Body request: Credentials): TokenResponse
    @POST("auth/refresh") fun refresh(@Body request: RefreshRequest): Call<TokenResponse>
    @POST("auth/logout") fun logout(@Body request: RefreshRequest): Call<Unit>
}

/** Retrofit contract. The authenticated client is supplied by [ReaderApiFactory]. */
interface ReaderApi {
    @POST("readings/generate") suspend fun generate(@Body request: GenerationRequest): GeneratedReading
    @GET("readings/{readingId}") suspend fun reading(@Path("readingId") readingId: String): GeneratedReading
    @GET("dictionary/{lemma}") suspend fun dictionary(@Path("lemma") lemma: String): DictionaryEntryDto
    @GET("readings/{readingId}/annotations") suspend fun annotations(@Path("readingId") readingId: String): List<AnnotationDto>
    @PUT("readings/{readingId}/annotations/{tokenId}") suspend fun saveAnnotation(@Path("readingId") readingId: String, @Path("tokenId") tokenId: String, @Body request: AnnotationInputDto): AnnotationDto
    @POST("learning-events") suspend fun syncEvents(@Body request: EventBatchRequest): EventBatchResponse
    @GET("learner-state") suspend fun learnerState(): List<LearnerWordStateDto>
    @GET("vocabulary") suspend fun vocabulary(): List<VocabularyDto>
    @POST("vocabulary") suspend fun createVocabulary(@Body request: VocabularyInputDto): VocabularyDto
    @PUT("vocabulary/{vocabularyId}") suspend fun updateVocabulary(@Path("vocabularyId") vocabularyId: String, @Body request: VocabularyInputDto): VocabularyDto
    @POST("imports/anki/preview") suspend fun previewImport(@Body request: ImportPreviewRequest): ImportPreviewResponse
    @POST("imports/anki") suspend fun importAnki(@Body request: ImportRequest): ImportResponse
}
