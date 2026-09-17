package com.gradedreader.korean

import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.text.HtmlCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewModelScope
import com.gradedreader.korean.data.ImportPreviewResponse
import com.gradedreader.korean.data.ImportResponse
import com.gradedreader.korean.data.SessionRepository
import com.gradedreader.korean.data.VocabularyEntity
import com.gradedreader.korean.data.VocabularyRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class VocabularyViewModel(private val repository: VocabularyRepository) : ViewModel() {
    val vocabulary = repository.vocabulary
    private val _working = MutableStateFlow(false)
    val working: StateFlow<Boolean> = _working
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error
    private val _summary = MutableStateFlow<ImportResponse?>(null)
    val summary: StateFlow<ImportResponse?> = _summary

    fun refresh() = run { _working.value = true; _error.value = null; viewModelScope.launch { try { repository.refresh() } catch (error: Exception) { _error.value = error.message ?: "Unable to load vocabulary" } finally { _working.value = false } } }
    fun save(term: String, meaning: String?) = run { _working.value = true; _error.value = null; viewModelScope.launch { try { repository.save(null, term, meaning, emptyList()) } catch (error: Exception) { _error.value = error.message ?: "Unable to save vocabulary" } finally { _working.value = false } } }
    fun preview(content: String, onReady: (ImportPreviewResponse) -> Unit) = viewModelScope.launch { try { onReady(repository.preview(content)) } catch (error: Exception) { _error.value = error.importMessage("Unable to preview import") } }
    fun import(content: String, filename: String, termColumn: String, meaningColumn: String) = run { _working.value = true; _error.value = null; viewModelScope.launch { try { _summary.value = repository.import(content, filename, termColumn, meaningColumn) } catch (error: Exception) { _error.value = error.importMessage("Unable to import vocabulary") } finally { _working.value = false } } }
}

private fun automaticVocabularyColumns(headers: List<String>): Pair<String, String>? {
    val contentHeaders = headers.filterNot { header ->
        header.trim().lowercase() in setOf("guid", "note type", "deck", "tags", "sentence", "translation", "notes", "audio", "picture")
    }
    val korean = headers.firstOrNull { it.trim().lowercase() in setOf("korean", "korean word", "term", "word", "front") }
        ?: contentHeaders.firstOrNull()
    val english = headers.firstOrNull { it.trim().lowercase() in setOf("english", "english word", "meaning", "definition", "gloss", "back") }
        ?: contentHeaders.firstOrNull { it != korean }
    return if (korean != null && english != null) korean to english else null
}
private fun Exception.importMessage(fallback: String): String = when (this) {
    is retrofit2.HttpException -> response()?.errorBody()?.string()?.let { body ->
        Regex("\\\"detail\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"").find(body)?.groupValues?.getOrNull(1)
    } ?: message()
    else -> message
}.orEmpty().ifBlank { fallback }
class VocabularyViewModelFactory(private val repository: VocabularyRepository) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST") override fun <T : ViewModel> create(modelClass: Class<T>): T = VocabularyViewModel(repository) as T
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VocabularyScreen(sessions: SessionRepository, onBack: () -> Unit) {
    val context = LocalContext.current
    val repository = remember(context, sessions) { VocabularyRepository.create(context, sessions) }
    val viewModel: VocabularyViewModel = viewModel(factory = VocabularyViewModelFactory(repository))
    val vocabulary by viewModel.vocabulary.collectAsState(emptyList())
    val working by viewModel.working.collectAsState()
    val error by viewModel.error.collectAsState()
    val summary by viewModel.summary.collectAsState()
    var term by rememberSaveable { mutableStateOf("") }
    var meaning by rememberSaveable { mutableStateOf("") }
    var importContent by rememberSaveable { mutableStateOf<String?>(null) }
    var importName by rememberSaveable { mutableStateOf("") }
    var termColumn by rememberSaveable { mutableStateOf("") }
    var meaningColumn by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(Unit) { viewModel.refresh() }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        uri?.let { selected ->
            readImport(context, selected)?.let { content ->
                importContent = content; importName = selected.lastPathSegment ?: "anki-export"
                viewModel.preview(content) { preview ->
                    automaticVocabularyColumns(preview.headers)?.let { (term, meaning) ->
                        termColumn = term
                        meaningColumn = meaning
                    } ?: run {
                        termColumn = ""
                        meaningColumn = ""
                    }
                }
            }
        }
    }
    Scaffold(topBar = { TopAppBar(title = { Text("Vocabulary") }, navigationIcon = { OutlinedButton(onClick = onBack) { Text("Back") } }) }) { padding ->
        LazyColumn(Modifier.padding(padding).padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item { Text("Add a term", style = MaterialTheme.typography.titleMedium) }
            item { OutlinedTextField(term, { term = it }, label = { Text("Korean term") }, modifier = Modifier.fillMaxWidth()) }
            item { OutlinedTextField(meaning, { meaning = it }, label = { Text("Meaning (optional)") }, modifier = Modifier.fillMaxWidth()) }
            item { Button(onClick = { viewModel.save(term, meaning.ifBlank { null }) }, enabled = term.isNotBlank() && !working) { Text("Add vocabulary") } }
            item { Text("Anki import", style = MaterialTheme.typography.titleMedium) }
            item { Text("Export notes from Anki as a text, CSV, or TSV file. Deck packages (.apkg) are not supported.", style = MaterialTheme.typography.bodySmall) }
            item { OutlinedButton(onClick = { picker.launch(arrayOf("text/plain", "text/csv", "text/tab-separated-values")) }, enabled = !working) { Text("Choose Anki export") } }
            if (importContent != null) {
                if (termColumn.isNotBlank() && meaningColumn.isNotBlank()) {
                    item { Text("Korean and English fields were selected automatically. Sentence, translation, notes, and media fields are ignored.", style = MaterialTheme.typography.bodySmall) }
                    item { Button(onClick = { viewModel.import(importContent.orEmpty(), importName, termColumn, meaningColumn) }, enabled = !working) { Text("Import $importName") } }
                } else {
                    item { Text("This export needs separate Korean and English fields.", color = MaterialTheme.colorScheme.error) }
                }
            }
            summary?.let { result -> item { Text("Import complete: ${result.imported} added, ${result.updated} updated, ${result.skipped} skipped.") } }
            error?.let { message -> item { Text(message, color = MaterialTheme.colorScheme.error) } }
            if (working) item { CircularProgressIndicator() }
            item { Text("Saved vocabulary", style = MaterialTheme.typography.titleMedium) }
            items(vocabulary, key = { it.id }) { item -> VocabularyRow(item) }
        }
    }
}

@Composable
private fun VocabularyRow(item: VocabularyEntity) {
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(primaryVocabularyText(item.term), style = MaterialTheme.typography.titleMedium)
        item.meaning?.let { meaning ->
            primaryVocabularyText(meaning).takeIf(String::isNotBlank)?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        }
    }
    HorizontalDivider()
}

private fun primaryVocabularyText(value: String): String = HtmlCompat.fromHtml(value, HtmlCompat.FROM_HTML_MODE_LEGACY)
    .toString()
    .lineSequence()
    .firstOrNull(String::isNotBlank)
    ?.trim()
    .orEmpty()

private fun readImport(context: Context, uri: Uri): String? = context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
