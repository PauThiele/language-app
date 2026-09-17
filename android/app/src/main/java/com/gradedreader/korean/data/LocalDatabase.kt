package com.gradedreader.korean.data

import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Transaction
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "readings") data class ReadingEntity(@PrimaryKey val id: String, val title: String, val text: String, val completed: Boolean = false, val genre: String? = null, val length: String? = null, val newWordIntensity: Int? = null, val grammarIntensity: Int? = null)
@Entity(tableName = "reading_content") data class ReadingContentEntity(@PrimaryKey val readingId: String, val content: String)
@Entity(tableName = "dictionary_entries") data class DictionaryEntryEntity(@PrimaryKey val lemma: String, val gloss: String, val englishTranslation: String?, val partOfSpeech: String?, val forms: String, val source: String)
@Entity(tableName = "learner_word_state", primaryKeys = ["lemma"]) data class LearnerWordStateEntity(val lemma: String, val confidence: Float = .35f, val encounters: Int = 0, val lookups: Int = 0, val correctAnswers: Int = 0, val incorrectAnswers: Int = 0)
@Entity(tableName = "annotations", primaryKeys = ["readingId", "tokenId"]) data class AnnotationEntity(val readingId: String, val tokenId: String, val note: String, val updatedAt: Long)
@Entity(tableName = "pending_events") data class PendingEventEntity(@PrimaryKey val id: String, val type: String, val payload: String, val occurredAt: Long, val attempts: Int = 0)
@Entity(tableName = "vocabulary") data class VocabularyEntity(@PrimaryKey val id: String, val term: String, val normalizedTerm: String, val meaning: String?, val tags: String)

@Dao interface ReaderDao {
    @Query("SELECT * FROM readings ORDER BY id DESC") fun readings(): Flow<List<ReadingEntity>>
    @Query("SELECT * FROM reading_content WHERE readingId = :readingId") fun readingContent(readingId: String): Flow<ReadingContentEntity?>
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun saveReading(reading: ReadingEntity)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun saveReadingContent(content: ReadingContentEntity)
    @Query("SELECT * FROM dictionary_entries WHERE lemma = :lemma") suspend fun dictionary(lemma: String): DictionaryEntryEntity?
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun saveDictionary(entry: DictionaryEntryEntity)
    @Query("SELECT * FROM learner_word_state WHERE lemma = :lemma") suspend fun learnerWordState(lemma: String): LearnerWordStateEntity?
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun saveLearnerWordState(state: LearnerWordStateEntity)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun saveLearnerWordStates(states: List<LearnerWordStateEntity>)
    @Query("DELETE FROM learner_word_state") suspend fun clearLearnerWordStates()
    @Transaction suspend fun replaceLearnerWordStates(states: List<LearnerWordStateEntity>) { clearLearnerWordStates(); saveLearnerWordStates(states) }
    @Query("UPDATE learner_word_state SET lookups = lookups + 1, confidence = MAX(0, confidence - 0.1) WHERE lemma = :lemma") suspend fun recordLookup(lemma: String)
    @Query("SELECT * FROM annotations WHERE readingId = :readingId AND tokenId = :tokenId") suspend fun annotation(readingId: String, tokenId: String): AnnotationEntity?
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun saveAnnotation(annotation: AnnotationEntity)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun enqueue(event: PendingEventEntity)
    @Query("SELECT * FROM pending_events ORDER BY occurredAt LIMIT :limit") suspend fun pendingEvents(limit: Int): List<PendingEventEntity>
    @Query("DELETE FROM pending_events WHERE id IN (:ids)") suspend fun removeEvents(ids: List<String>)
    @Query("UPDATE pending_events SET attempts = attempts + 1 WHERE id IN (:ids)") suspend fun incrementAttempts(ids: List<String>)
    @Query("SELECT * FROM vocabulary ORDER BY normalizedTerm") fun vocabulary(): Flow<List<VocabularyEntity>>
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun saveVocabulary(items: List<VocabularyEntity>)
    @Query("DELETE FROM vocabulary") suspend fun clearVocabulary()
    @Transaction suspend fun replaceVocabulary(items: List<VocabularyEntity>) { clearVocabulary(); saveVocabulary(items) }
}

@Database(entities = [ReadingEntity::class, ReadingContentEntity::class, DictionaryEntryEntity::class, LearnerWordStateEntity::class, AnnotationEntity::class, PendingEventEntity::class, VocabularyEntity::class], version = 7, exportSchema = true)
abstract class LocalDatabase : RoomDatabase() { abstract fun readerDao(): ReaderDao }

object LocalDatabaseFactory {
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
    private val migration4To5 = object : Migration(4, 5) {
        override fun migrate(database: SupportSQLiteDatabase) {
            database.execSQL("ALTER TABLE `learner_word_state` ADD COLUMN `correctAnswers` INTEGER NOT NULL DEFAULT 0")
            database.execSQL("ALTER TABLE `learner_word_state` ADD COLUMN `incorrectAnswers` INTEGER NOT NULL DEFAULT 0")
        }
    }
    private val migration5To6 = object : Migration(5, 6) {
        override fun migrate(database: SupportSQLiteDatabase) {
            database.execSQL("ALTER TABLE `dictionary_entries` ADD COLUMN `englishTranslation` TEXT")
        }
    }
    private val migration6To7 = object : Migration(6, 7) {
        override fun migrate(database: SupportSQLiteDatabase) {
            database.execSQL("ALTER TABLE `readings` ADD COLUMN `genre` TEXT")
            database.execSQL("ALTER TABLE `readings` ADD COLUMN `length` TEXT")
            database.execSQL("ALTER TABLE `readings` ADD COLUMN `newWordIntensity` INTEGER")
            database.execSQL("ALTER TABLE `readings` ADD COLUMN `grammarIntensity` INTEGER")
        }
    }

    fun create(context: android.content.Context): LocalDatabase = Room.databaseBuilder(context.applicationContext, LocalDatabase::class.java, "reader.db")
        .addMigrations(migration2To3, migration3To4, migration4To5, migration5To6, migration6To7)
        .build()
}
