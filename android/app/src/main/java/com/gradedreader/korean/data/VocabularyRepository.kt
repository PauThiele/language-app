package com.gradedreader.korean.data

import android.content.Context
import androidx.room.Room
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

class VocabularyRepository private constructor(private val dao: ReaderDao, private val api: ReaderApi) {
    val vocabulary: Flow<List<VocabularyEntity>> = dao.vocabulary()

    suspend fun refresh() {
        dao.replaceVocabulary(api.vocabulary().map { it.toEntity() })
    }

    suspend fun save(id: String?, term: String, meaning: String?, tags: List<String>) {
        val request = VocabularyInputDto(term, meaning, tags)
        val saved = if (id == null) api.createVocabulary(request) else api.updateVocabulary(id, request)
        dao.saveVocabulary(listOf(saved.toEntity()))
    }

    suspend fun preview(content: String): ImportPreviewResponse = api.previewImport(ImportPreviewRequest(content))

    suspend fun import(content: String, filename: String, termColumn: String, meaningColumn: String): ImportResponse {
        val delimiter = when (content.lineSequence().firstOrNull().orEmpty().removePrefix("\uFEFF").trim().lowercase()) {
            "#separator:tab" -> "\t"
            "#separator:comma" -> ","
            else -> if (content.lineSequence().firstOrNull().orEmpty().contains('\t')) "\t" else ","
        }
        val summary = api.importAnki(ImportRequest(content, delimiter, filename, termColumn, meaningColumn))
        refresh()
        return summary
    }

    private fun VocabularyDto.toEntity() = VocabularyEntity(id, term, normalizedTerm, meaning, json.encodeToString(tags))

    companion object {
        private val json = Json
        private val migration2To3 = object : Migration(2, 3) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL("CREATE TABLE IF NOT EXISTS `reading_content` (`readingId` TEXT NOT NULL, `content` TEXT NOT NULL, PRIMARY KEY(`readingId`))")
            }
        }
        private val migration3To4 = object : Migration(3, 4) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL("CREATE TABLE IF NOT EXISTS `vocabulary` (`id` TEXT NOT NULL, `term` TEXT NOT NULL, `normalizedTerm` TEXT NOT NULL, `meaning` TEXT, `tags` TEXT NOT NULL, PRIMARY KEY(`id`))")
            }
        }

        fun create(context: Context, tokenProvider: AccessTokenProvider): VocabularyRepository {
            val database = Room.databaseBuilder(context.applicationContext, LocalDatabase::class.java, "reader.db")
                .addMigrations(migration2To3, migration3To4)
                .build()
            return VocabularyRepository(database.readerDao(), ReaderApiFactory.create(tokenProvider))
        }
    }
}
