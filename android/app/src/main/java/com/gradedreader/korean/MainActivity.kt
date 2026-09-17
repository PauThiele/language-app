package com.gradedreader.korean

import android.os.Bundle
import android.content.Context
import android.os.SystemClock
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.gradedreader.korean.data.AuthApi
import com.gradedreader.korean.data.Credentials
import com.gradedreader.korean.data.GeneratedReading
import com.gradedreader.korean.data.GeneratedQuestion
import com.gradedreader.korean.data.GenerationRequest
import com.gradedreader.korean.data.GeneratedToken
import com.gradedreader.korean.data.DictionaryEntryEntity
import com.gradedreader.korean.data.ReaderApiFactory
import com.gradedreader.korean.data.ReaderRepository
import com.gradedreader.korean.data.SessionRepository
import com.gradedreader.korean.learning.EventSyncScheduler
import com.gradedreader.korean.settings.SettingsRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import retrofit2.HttpException
import java.io.IOException

sealed interface ReaderUiState {
    data object Empty : ReaderUiState
    data object Loading : ReaderUiState
    data class Ready(val reading: GeneratedReading) : ReaderUiState
    data class Error(val message: String) : ReaderUiState
}

sealed interface DictionaryUiState {
    data object Idle : DictionaryUiState
    data class Loading(val readingId: String, val token: GeneratedToken) : DictionaryUiState
    data class Ready(val readingId: String, val token: GeneratedToken, val entry: DictionaryEntryEntity, val grammar: List<KoreanGrammarMatch>, val note: String) : DictionaryUiState
    data class Error(val readingId: String, val token: GeneratedToken, val message: String) : DictionaryUiState
}

class ReaderViewModel(private val repository: ReaderRepository) : ViewModel() {
    val savedReadings = repository.savedReadings
    private val _uiState = MutableStateFlow<ReaderUiState>(ReaderUiState.Empty)
    val uiState: StateFlow<ReaderUiState> = _uiState.asStateFlow()
    private val _dictionaryState = MutableStateFlow<DictionaryUiState>(DictionaryUiState.Idle)
    val dictionaryState: StateFlow<DictionaryUiState> = _dictionaryState.asStateFlow()
    private val answers = mutableStateMapOf<String, String>()
    private val answerStartedAtMillis = mutableMapOf<String, Long>()
    private val answerElapsedSeconds = mutableStateMapOf<String, Long>()
    private val lookedUpLemmas = mutableSetOf<String>()

    fun generate(request: GenerationRequest) = viewModelScope.launch {
        _uiState.value = ReaderUiState.Loading
        try {
            showReading(repository.generate(request))
        } catch (error: Exception) {
            _uiState.value = ReaderUiState.Error(error.readerMessage())
        }
    }

    fun openSaved(readingId: String) = viewModelScope.launch {
        repository.savedReading(readingId).first()?.let { showReading(it) }
    }

    fun beginAnswerTiming(questionId: String, enabled: Boolean) {
        if (enabled && questionId !in answers) answerStartedAtMillis.putIfAbsent(questionId, SystemClock.elapsedRealtime())
    }

    fun answer(reading: GeneratedReading, question: GeneratedQuestion, optionId: String, answerTimingEnabled: Boolean) {
        if (question.id in answers) return
        answers[question.id] = optionId
        if (answerTimingEnabled) {
            val startedAt = answerStartedAtMillis.remove(question.id) ?: SystemClock.elapsedRealtime()
            answerElapsedSeconds[question.id] = ((SystemClock.elapsedRealtime() - startedAt) / MILLIS_PER_SECOND).coerceAtLeast(0)
        }
        viewModelScope.launch {
            repository.recordQuestionAnswer(reading, question, optionId, question.targetLemmas.any(lookedUpLemmas::contains))
        }
    }
    fun selectedAnswer(questionId: String): String? = answers[questionId]
    fun answerElapsedSeconds(questionId: String): Long? = answerElapsedSeconds[questionId]

    fun lookup(readingId: String, token: GeneratedToken) = viewModelScope.launch {
        _dictionaryState.value = DictionaryUiState.Loading(readingId, token)
        try {
            val entry = repository.lookup(readingId, token)
            lookedUpLemmas += entry.lemma
            _dictionaryState.value = DictionaryUiState.Ready(readingId, token, entry, KoreanGrammarDetector.detect(token.surface), repository.annotation(readingId, token.id)?.note.orEmpty())
        } catch (error: Exception) {
            _dictionaryState.value = DictionaryUiState.Error(readingId, token, error.lookupMessage())
        }
    }

    private suspend fun showReading(reading: GeneratedReading) {
        answers.clear()
        answerStartedAtMillis.clear()
        answerElapsedSeconds.clear()
        lookedUpLemmas.clear()
        repository.recordReadingOpened(reading)
        _uiState.value = ReaderUiState.Ready(reading)
    }
    fun saveAnnotation(readingId: String, tokenId: String, note: String) = viewModelScope.launch {
        if (note.isNotBlank()) repository.saveAnnotation(readingId, tokenId, note)
    }

    fun dismissDictionary() { _dictionaryState.value = DictionaryUiState.Idle }

    private fun Exception.readerMessage() = when (this) {
        is IOException -> "Generation is unavailable while offline. Saved readings remain available."
        is HttpException -> when (code()) {
            401 -> "Your session ended. Sign in again to generate a reading."
            429 -> "Today's generation limit has been reached."
            503 -> "The generation service is temporarily unavailable. Try again later."
            422 -> generationValidationMessage() ?: "The generated reading was incomplete. Please try again."
            else -> "Could not generate a reading (server error ${code()})."
        }
        else -> "Could not generate a reading. Please try again."
    }

    private fun HttpException.generationValidationMessage(): String? = runCatching {
        JSONObject(response()?.errorBody()?.string().orEmpty())
            .optString("detail")
            .trim()
            .takeIf { it.isNotEmpty() }
            ?.let { "Could not generate a reading: $it" }
    }.getOrNull()

    private fun Exception.lookupMessage() = when (this) {
        is IOException -> "Dictionary data is unavailable offline and this word has not been cached yet."
        is HttpException -> "Could not look up this word (server error ${code()})."
        else -> "Could not look up this word. Please try again."
    }

    private companion object {
        const val MILLIS_PER_SECOND = 1_000L
    }
}

class ReaderViewModelFactory(private val repository: ReaderRepository) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST") override fun <T : ViewModel> create(modelClass: Class<T>): T = ReaderViewModel(repository) as T
}

class SessionViewModel(private val sessions: SessionRepository, private val api: AuthApi, private val context: Context) : ViewModel() {
    val session = sessions.session
    private val _working = MutableStateFlow(false)
    val working: StateFlow<Boolean> = _working.asStateFlow()
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    fun signIn(email: String, password: String, register: Boolean) = viewModelScope.launch {
        _working.value = true
        _error.value = null
        try {
            val tokens = withContext(Dispatchers.IO) {
                if (register) api.register(Credentials(email, password)) else api.login(Credentials(email, password))
            }
            sessions.save(tokens)
            sessions.rememberEmail(email)
            EventSyncScheduler.schedule(context)
        } catch (error: Exception) {
            _error.value = when (error) {
                is IOException -> "Sign-in is unavailable while offline."
                is HttpException -> when (error.code()) {
                    401 -> "Invalid email or password."
                    409 -> "That email is already registered."
                    422 -> "Use a valid email and a password with at least 10 characters."
                    else -> "Could not sign in (server error ${error.code()})."
                }
                else -> "Could not sign in. Please try again."
            }
        } finally {
            _working.value = false
        }
    }

    fun signOut() = viewModelScope.launch {
        _working.value = true
        try {
            withContext(Dispatchers.IO) { sessions.session.value?.let { api.logout(com.gradedreader.korean.data.RefreshRequest(it.refreshToken)).execute() } }
        } finally {
            sessions.clear()
            _working.value = false
        }
    }
}

class SessionViewModelFactory(private val sessions: SessionRepository, private val api: AuthApi, private val context: Context) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST") override fun <T : ViewModel> create(modelClass: Class<T>): T = SessionViewModel(sessions, api, context.applicationContext) as T
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme { ReaderApp() } }
    }
}

@Composable
private fun ReaderApp() {
    val context = LocalContext.current
    val sessions = remember(context) { SessionRepository.create(context) }
    val sessionViewModel: SessionViewModel = viewModel(factory = SessionViewModelFactory(sessions, ReaderApiFactory.authApi(), context))
    val session by sessionViewModel.session.collectAsState()
    val rememberedEmails by sessions.rememberedEmails.collectAsState(emptyList())
    val working by sessionViewModel.working.collectAsState()
    val error by sessionViewModel.error.collectAsState()
    ReaderScreen(
        sessions = sessions,
        signedIn = session != null,
        signingOut = working,
        signInWorking = working,
        signInError = error,
        rememberedEmails = rememberedEmails,
        onSignIn = sessionViewModel::signIn,
        onForgetRememberedEmail = sessions::forgetEmail,
        onSignOut = sessionViewModel::signOut,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AuthScreen(
    working: Boolean,
    error: String?,
    rememberedEmails: List<String>,
    onBack: () -> Unit,
    onForgetRememberedEmail: (String) -> Unit,
    onSubmit: (String, String, Boolean) -> Unit,
) {
    var email by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var passwordVisible by rememberSaveable { mutableStateOf(false) }
    var registering by rememberSaveable { mutableStateOf(false) }
    Scaffold(topBar = {
        TopAppBar(
            title = { Text(if (registering) "Create account" else "Sign in") },
            navigationIcon = { TextButton(onClick = onBack) { Text("Back") } },
        )
    }) { padding ->
        Column(Modifier.padding(padding).padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Sign in to generate new readings. Saved readings remain available on this device.")
            if (!registering && rememberedEmails.isNotEmpty()) {
                Text("Saved accounts")
                rememberedEmails.forEach { rememberedEmail ->
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = { email = rememberedEmail }) { Text(rememberedEmail) }
                        TextButton(onClick = { onForgetRememberedEmail(rememberedEmail) }) { Text("Remove") }
                    }
                }
            }
            OutlinedTextField(email, { email = it }, label = { Text("Email") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("Password") },
                visualTransformation = if (passwordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                trailingIcon = {
                    TextButton(onClick = { passwordVisible = !passwordVisible }) {
                        Text(if (passwordVisible) "Hide" else "Show")
                    }
                },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Button(onClick = { onSubmit(email.trim(), password, registering) }, enabled = !working, modifier = Modifier.fillMaxWidth()) {
                if (working) CircularProgressIndicator() else Text(if (registering) "Create account" else "Sign in")
            }
            OutlinedButton(onClick = { registering = !registering }, enabled = !working, modifier = Modifier.fillMaxWidth()) {
                Text(if (registering) "I already have an account" else "Create an account")
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ReaderScreen(
    sessions: SessionRepository,
    signedIn: Boolean,
    signingOut: Boolean,
    signInWorking: Boolean,
    signInError: String?,
    rememberedEmails: List<String>,
    onSignIn: (String, String, Boolean) -> Unit,
    onForgetRememberedEmail: (String) -> Unit,
    onSignOut: () -> Unit,
) {
    val context = LocalContext.current
    val repository = remember(context, sessions) { ReaderRepository.create(context, sessions) }
    val vm: ReaderViewModel = viewModel(factory = ReaderViewModelFactory(repository))
    val state by vm.uiState.collectAsState()
    val dictionaryState by vm.dictionaryState.collectAsState()
    val savedReadings by vm.savedReadings.collectAsState(emptyList())
    val settingsRepository = remember(context) { SettingsRepository(context.applicationContext) }
    val answerTimingEnabled by settingsRepository.answerTimeEnabled.collectAsState(initial = false)
    val selectedGenerationModel by settingsRepository.selectedGenerationModel.collectAsState(initial = "")
    val scope = rememberCoroutineScope()
    var genre by rememberSaveable { mutableStateOf("daily life") }
    var length by rememberSaveable { mutableStateOf("short") }
    var newWordIntensity by rememberSaveable { mutableStateOf("2") }
    var grammarIntensity by rememberSaveable { mutableStateOf("2") }
    val generationRequest = GenerationRequest(
        genre = genre.trim().ifBlank { "daily life" },
        length = if (length in listOf("short", "medium", "long")) length else "short",
        newWordIntensity = newWordIntensity.toIntOrNull()?.coerceIn(0, 5) ?: 2,
        grammarIntensity = grammarIntensity.toIntOrNull()?.coerceIn(0, 5) ?: 2,
        model = selectedGenerationModel.ifBlank { null },
    )
    var showingVocabulary by rememberSaveable { mutableStateOf(false) }
    var showingSettings by rememberSaveable { mutableStateOf(false) }
    var showingSignIn by rememberSaveable { mutableStateOf(false) }
    var savedReadingsExpanded by rememberSaveable { mutableStateOf(false) }
    var savedReadingsSearch by rememberSaveable { mutableStateOf("") }
    var savedReadingsFiltersExpanded by rememberSaveable { mutableStateOf(false) }
    var savedReadingsGenreFilter by rememberSaveable { mutableStateOf("") }
    var savedReadingsLengthFilter by rememberSaveable { mutableStateOf("Any") }
    var savedReadingsNewWordIntensityFilter by rememberSaveable { mutableStateOf("Any") }
    var savedReadingsGrammarIntensityFilter by rememberSaveable { mutableStateOf("Any") }
    var scrollToReadingOnOpen by remember { mutableStateOf(false) }
    val readingListState = rememberLazyListState()
    val readyReading = (state as? ReaderUiState.Ready)?.reading
    val savedReadingsQuery = savedReadingsSearch.trim()
    val matchingSavedReadings = savedReadings.filter { reading ->
        (savedReadingsQuery.isBlank() ||
            reading.title.contains(savedReadingsQuery, ignoreCase = true) ||
            reading.text.contains(savedReadingsQuery, ignoreCase = true)) &&
            (savedReadingsGenreFilter.isBlank() || reading.genre?.contains(savedReadingsGenreFilter.trim(), ignoreCase = true) == true) &&
            (savedReadingsLengthFilter == "Any" || reading.length == savedReadingsLengthFilter) &&
            (savedReadingsNewWordIntensityFilter == "Any" || reading.newWordIntensity?.toString() == savedReadingsNewWordIntensityFilter) &&
            (savedReadingsGrammarIntensityFilter == "Any" || reading.grammarIntensity?.toString() == savedReadingsGrammarIntensityFilter)
    }
    val allQuestionsAnswered = readyReading?.let { reading ->
        reading.questions.isNotEmpty() && reading.questions.all { vm.selectedAnswer(it.id) != null }
    } == true
    var comprehensionExpanded by rememberSaveable(readyReading?.id) { mutableStateOf(true) }
    LaunchedEffect(signedIn) {
        if (signedIn) showingSignIn = false
    }
    LaunchedEffect(readyReading?.id, allQuestionsAnswered) {
        if (allQuestionsAnswered) {
            comprehensionExpanded = false
            readingListState.animateScrollToItem(1)
        }
    }
    LaunchedEffect(readyReading?.id) {
        if (scrollToReadingOnOpen && readyReading != null) {
            readingListState.animateScrollToItem(1)
            scrollToReadingOnOpen = false
        }
    }
    if (showingSignIn) {
        AuthScreen(
            working = signInWorking,
            error = signInError,
            rememberedEmails = rememberedEmails,
            onBack = { showingSignIn = false },
            onForgetRememberedEmail = onForgetRememberedEmail,
            onSubmit = onSignIn,
        )
        return
    }
    if (showingVocabulary) {
        VocabularyScreen(sessions, onBack = { showingVocabulary = false })
        return
    }
    Scaffold(topBar = {
        Column {
            TopAppBar(title = { Text("Graded Reader") })
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedButton(onClick = { showingVocabulary = true }) { Text("Vocabulary") }
                OutlinedButton(onClick = { showingSettings = true }) { Text("Settings") }
                if (signedIn) {
                    OutlinedButton(onClick = onSignOut, enabled = !signingOut) { Text("Sign out") }
                } else {
                    OutlinedButton(onClick = { showingSignIn = true }) { Text("Sign in") }
                }
            }
        }
    }) { padding ->
        LazyColumn(state = readingListState, modifier = Modifier.padding(padding).padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Reading controls", style = MaterialTheme.typography.titleMedium)
                    if (signedIn) Text("Signed in — ready to generate.", color = MaterialTheme.colorScheme.primary)
                    OutlinedTextField(genre, { genre = it }, label = { Text("Genre") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    SelectionSelector("Length", length, listOf("short", "medium", "long")) { length = it }
                    SelectionSelector("New-word intensity", newWordIntensity, (0..5).map(Int::toString)) { newWordIntensity = it }
                    SelectionSelector("Grammar intensity", grammarIntensity, (0..5).map(Int::toString)) { grammarIntensity = it }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Button(onClick = { vm.generate(generationRequest) }, enabled = signedIn && state !is ReaderUiState.Loading) { Text("Generate reading") }
                        if (state is ReaderUiState.Error) OutlinedButton(onClick = { vm.generate(generationRequest) }, enabled = signedIn) { Text("Retry") }
                    }
                    if (!signedIn) Text("Sign in to generate new readings. Saved readings are available below.")
                }
            }
            when (val current = state) {
                ReaderUiState.Empty -> item { Text("Generate a reading or open a saved reading below.") }
                ReaderUiState.Loading -> item { CircularProgressIndicator() }
                is ReaderUiState.Error -> item { Text(current.message, color = MaterialTheme.colorScheme.error) }
                is ReaderUiState.Ready -> readerItems(
                    reading = current.reading,
                    vm = vm,
                    answerTimingEnabled = answerTimingEnabled,
                    allQuestionsAnswered = allQuestionsAnswered,
                    comprehensionExpanded = comprehensionExpanded,
                    onComprehensionExpandedChange = { comprehensionExpanded = it },
                )
            }
            if (savedReadings.isNotEmpty()) {
                item {
                    TextButton(onClick = { savedReadingsExpanded = !savedReadingsExpanded }) {
                        Text(if (savedReadingsExpanded) "Hide saved readings" else "Show saved readings")
                    }
                }
                if (savedReadingsExpanded) {
                    item { Text("Saved readings", style = MaterialTheme.typography.titleMedium) }
                    item {
                        OutlinedTextField(
                            value = savedReadingsSearch,
                            onValueChange = { savedReadingsSearch = it },
                            label = { Text("Search saved readings") },
                            placeholder = { Text("Title or text") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    item {
                        TextButton(onClick = { savedReadingsFiltersExpanded = !savedReadingsFiltersExpanded }) {
                            Text(if (savedReadingsFiltersExpanded) "Hide filters" else "Filter saved readings")
                        }
                    }
                    if (savedReadingsFiltersExpanded) {
                        item {
                            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                OutlinedTextField(
                                    value = savedReadingsGenreFilter,
                                    onValueChange = { savedReadingsGenreFilter = it },
                                    label = { Text("Genre filter") },
                                    placeholder = { Text("Any genre") },
                                    singleLine = true,
                                    modifier = Modifier.fillMaxWidth(),
                                )
                                SelectionSelector("Length filter", savedReadingsLengthFilter, listOf("Any", "short", "medium", "long")) { savedReadingsLengthFilter = it }
                                SelectionSelector("New-word intensity filter", savedReadingsNewWordIntensityFilter, listOf("Any") + (0..5).map(Int::toString)) { savedReadingsNewWordIntensityFilter = it }
                                SelectionSelector("Grammar intensity filter", savedReadingsGrammarIntensityFilter, listOf("Any") + (0..5).map(Int::toString)) { savedReadingsGrammarIntensityFilter = it }
                            }
                        }
                    }
                    if (matchingSavedReadings.isEmpty()) {
                        item { Text("No saved readings match your search or filters.") }
                    } else {
                        items(matchingSavedReadings, key = { it.id }) { reading ->
                            Card(
                                onClick = { scrollToReadingOnOpen = true; vm.openSaved(reading.id) },
                                modifier = Modifier.fillMaxWidth(),
                            ) {
                                Column(Modifier.padding(12.dp)) {
                                    Text(reading.title)
                                    Text(reading.text, maxLines = 2)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    DictionaryDialog(dictionaryState, vm)
    if (showingSettings) {
        var generationModel by rememberSaveable { mutableStateOf(selectedGenerationModel) }
        AlertDialog(
            onDismissRequest = { showingSettings = false },
            title = { Text("Reader settings") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Show answer time")
                            Text("Display elapsed time after answering a comprehension question.", style = MaterialTheme.typography.bodySmall)
                        }
                        Switch(
                            checked = answerTimingEnabled,
                            onCheckedChange = { enabled -> scope.launch { settingsRepository.setAnswerTimeEnabled(enabled) } },
                        )
                    }
                    OutlinedTextField(
                        value = generationModel,
                        onValueChange = { generationModel = it },
                        label = { Text("Generation model") },
                        supportingText = { Text("Leave blank to use the backend provider default.") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            },
            confirmButton = { Button(onClick = { scope.launch { settingsRepository.setSelectedGenerationModel(generationModel) }; showingSettings = false }) { Text("Done") } },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SelectionSelector(label: String, value: String, options: List<String>, onValueChange: (String) -> Unit) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = value,
            onValueChange = {},
            readOnly = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option) },
                    onClick = {
                        onValueChange(option)
                        expanded = false
                    },
                )
            }
        }
    }
}

private const val tokenAnnotationTag = "reader-token"
private val readerWordPattern = Regex("[가-힣]+")

private data class ReadingWord(val token: GeneratedToken, val start: Int, val end: Int)

@Composable
private fun ReadingText(reading: GeneratedReading, onLookup: (GeneratedToken) -> Unit) {
    var layoutResult by remember(reading.id) { mutableStateOf<TextLayoutResult?>(null) }
    val words = remember(reading) {
        readerWordPattern.findAll(reading.text).map { match ->
            val surface = match.value
            val knownToken = reading.tokens.firstOrNull { it.surface == surface }
            ReadingWord(
                token = GeneratedToken(
                    id = knownToken?.id ?: "word-${match.range.first}",
                    surface = surface,
                    lemma = knownToken?.lemma ?: surface,
                    sentenceId = knownToken?.sentenceId.orEmpty(),
                ),
                start = match.range.first,
                end = match.range.last + 1,
            )
        }.toList()
    }
    val annotatedText = remember(reading.text, words) {
        buildAnnotatedString {
            var copiedUntil = 0
            words.forEach { word ->
                append(reading.text.substring(copiedUntil, word.start))
                pushStringAnnotation(tokenAnnotationTag, word.token.id)
                append(word.token.surface)
                pop()
                copiedUntil = word.end
            }
            append(reading.text.substring(copiedUntil))
        }
    }
    fun lookupAt(position: androidx.compose.ui.geometry.Offset) {
        layoutResult?.getOffsetForPosition(position)?.let { offset ->
            val annotations = annotatedText.getStringAnnotations(tokenAnnotationTag, offset, offset)
                .ifEmpty { annotatedText.getStringAnnotations(tokenAnnotationTag, (offset - 1).coerceAtLeast(0), (offset - 1).coerceAtLeast(0)) }
            annotations.firstOrNull()?.let { annotation ->
                words.firstOrNull { it.token.id == annotation.item }?.token?.let(onLookup)
            }
        }
    }
    Text(
        text = annotatedText,
        style = MaterialTheme.typography.bodyLarge,
        onTextLayout = { layoutResult = it },
        modifier = Modifier.pointerInput(annotatedText) {
            detectTapGestures(onTap = ::lookupAt, onLongPress = ::lookupAt)
        },
    )
}

private fun LazyListScope.readerItems(
    reading: GeneratedReading,
    vm: ReaderViewModel,
    answerTimingEnabled: Boolean,
    allQuestionsAnswered: Boolean,
    comprehensionExpanded: Boolean,
    onComprehensionExpandedChange: (Boolean) -> Unit,
) {
    item { Text(reading.title, style = MaterialTheme.typography.headlineSmall) }
    item { ReadingText(reading, onLookup = { token -> vm.lookup(reading.id, token) }) }
    item { Text("Tap a word for its dictionary entry.", style = MaterialTheme.typography.bodySmall) }
    if (reading.rationale.isNotBlank() || reading.targetLemmas.isNotEmpty() || reading.targetGrammar.isNotEmpty()) {
        item { LearningDetails(reading) }
    }
    if (allQuestionsAnswered && reading.englishTranslation.isNotBlank()) {
        item { CompletedReadingTranslation(reading) }
    }
    item { Text("Comprehension check", style = MaterialTheme.typography.titleLarge) }
    if (allQuestionsAnswered) {
        item {
            Column {
                val correctAnswers = reading.questions.count { question ->
                    vm.selectedAnswer(question.id) == question.correctOptionId
                }
                Text(
                    "$correctAnswers/${reading.questions.size} correct",
                    color = MaterialTheme.colorScheme.primary,
                )
                TextButton(onClick = { onComprehensionExpandedChange(!comprehensionExpanded) }) {
                    Text(if (comprehensionExpanded) "Hide answered questions" else "Show answered questions")
                }
            }
        }
    }
    if (!allQuestionsAnswered || comprehensionExpanded) {
        items(reading.questions, key = { it.id }) { question ->
            val selectedAnswer = vm.selectedAnswer(question.id)
            val displayedOptions = remember(question.id, question.options) { question.options.shuffled() }
            var showingEnglish by rememberSaveable(reading.id, question.id) { mutableStateOf(false) }
            LaunchedEffect(question.id, answerTimingEnabled) { vm.beginAnswerTiming(question.id, answerTimingEnabled) }
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(question.prompt, style = MaterialTheme.typography.titleMedium)
                    displayedOptions.forEach { option ->
                        OutlinedButton(
                            onClick = { vm.answer(reading, question, option.id, answerTimingEnabled) },
                            enabled = selectedAnswer == null,
                            modifier = Modifier.fillMaxWidth(),
                        ) { Text(option.text) }
                    }
                    if (selectedAnswer != null) {
                        val correct = selectedAnswer == question.correctOptionId
                        val correctAnswer = question.options.firstOrNull { it.id == question.correctOptionId }?.text.orEmpty()
                        vm.answerElapsedSeconds(question.id)?.let { Text("Answer time: ${it}s") }
                        Text(
                            if (correct) "Correct!" else "Not quite. Correct answer: $correctAnswer",
                            color = if (correct) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                        )
                        Text(question.explanation, color = MaterialTheme.colorScheme.primary)
                        TextButton(onClick = { showingEnglish = !showingEnglish }) {
                            Text(if (showingEnglish) "Hide English translation" else "Show English translation")
                        }
                        if (showingEnglish) {
                            Text("Question: ${question.englishTranslation}")
                            Text("Explanation: ${question.englishExplanation}")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun LearningDetails(reading: GeneratedReading) {
    var expanded by rememberSaveable(reading.id) { mutableStateOf(false) }
    TextButton(onClick = { expanded = !expanded }) {
        Text(if (expanded) "Hide learning details" else "Show learning details")
    }
    if (expanded) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            if (reading.rationale.isNotBlank()) {
                Text(reading.rationale)
            }
            if (reading.targetLemmas.isNotEmpty()) {
                Text("Vocabulary", style = MaterialTheme.typography.titleSmall)
                Text(reading.targetLemmas.joinToString())
            }
            if (reading.targetGrammar.isNotEmpty()) {
                Text("Grammar", style = MaterialTheme.typography.titleSmall)
                Text(reading.targetGrammar.joinToString())
            }
        }
    }
}

@Composable
private fun CompletedReadingTranslation(reading: GeneratedReading) {
    var showingTranslation by rememberSaveable(reading.id) { mutableStateOf(false) }
    TextButton(onClick = { showingTranslation = !showingTranslation }) {
        Text(if (showingTranslation) "Hide full English translation" else "Show full English translation")
    }
    if (showingTranslation) {
        Text(reading.englishTitle.ifBlank { "English translation" }, style = MaterialTheme.typography.titleLarge)
        Text(reading.englishTranslation, style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
private fun DictionaryDialog(state: DictionaryUiState, vm: ReaderViewModel) {
    when (state) {
        DictionaryUiState.Idle -> Unit
        is DictionaryUiState.Loading -> AlertDialog(onDismissRequest = vm::dismissDictionary, title = { Text(state.token.surface) }, text = { CircularProgressIndicator() }, confirmButton = {})
        is DictionaryUiState.Error -> AlertDialog(onDismissRequest = vm::dismissDictionary, title = { Text(state.token.surface) }, text = { Text(state.message) }, confirmButton = { Button(onClick = { vm.dismissDictionary() }) { Text("Close") } })
        is DictionaryUiState.Ready -> {
            var note by remember(state.token.id, state.note) { mutableStateOf(state.note) }
            AlertDialog(
                onDismissRequest = vm::dismissDictionary,
                title = { Text("Word details") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Text form: ${state.token.surface}")
                        if (state.token.surface != state.entry.lemma) Text("Dictionary form: ${state.entry.lemma}")
                        Text(state.entry.gloss)
                        state.entry.englishTranslation?.let {
                            Text("English: $it", color = MaterialTheme.colorScheme.primary)
                        }
                        state.entry.partOfSpeech?.let { Text(it) }
                        if (state.grammar.isNotEmpty()) {
                            Text("Grammar", style = MaterialTheme.typography.titleSmall)
                            state.grammar.forEach { grammar -> Text("${grammar.pattern}: ${grammar.meaning}") }
                        }
                        Text("Source: ${state.entry.source}")
                        OutlinedTextField(note, { note = it }, label = { Text("Token note") }, modifier = Modifier.fillMaxWidth())
                    }
                },
                confirmButton = { Button(onClick = { vm.saveAnnotation(state.readingId, state.token.id, note); vm.dismissDictionary() }, enabled = note.isNotBlank()) { Text("Save note") } },
                dismissButton = { OutlinedButton(onClick = vm::dismissDictionary) { Text("Close") } },
            )
        }
    }
}
