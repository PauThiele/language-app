package com.gradedreader.korean.settings

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.settingsDataStore by preferencesDataStore("reader_settings")

class SettingsRepository(private val context: Context) {
    private val useAnswerTime = booleanPreferencesKey("use_answer_time")
    private val generationModel = stringPreferencesKey("generation_model")
    val answerTimeEnabled: Flow<Boolean> = context.settingsDataStore.data.map { it[useAnswerTime] ?: false }
    val selectedGenerationModel: Flow<String> = context.settingsDataStore.data.map { it[generationModel].orEmpty() }
    suspend fun setAnswerTimeEnabled(enabled: Boolean) { context.settingsDataStore.edit { it[useAnswerTime] = enabled } }
    suspend fun setSelectedGenerationModel(model: String) { context.settingsDataStore.edit { it[generationModel] = model.trim() } }
}
