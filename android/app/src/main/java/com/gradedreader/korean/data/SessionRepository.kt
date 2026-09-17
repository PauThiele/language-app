package com.gradedreader.korean.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class AuthSession(val accessToken: String, val refreshToken: String)

class SessionRepository private constructor(context: Context) : AccessTokenProvider {
    private val storage = EncryptedSessionStorage(context.applicationContext)
    private val _session = MutableStateFlow(storage.read())
    val session: StateFlow<AuthSession?> = _session.asStateFlow()
    private val _rememberedEmails = MutableStateFlow(storage.readRememberedEmails())
    val rememberedEmails: StateFlow<List<String>> = _rememberedEmails.asStateFlow()

    override fun accessToken(): String? = _session.value?.accessToken

    fun save(tokens: TokenResponse) {
        save(AuthSession(tokens.accessToken, tokens.refreshToken))
    }

    fun save(session: AuthSession) {
        storage.write(session)
        _session.value = session
    }

    fun clear() {
        storage.clear()
        _session.value = null
    }

    fun rememberEmail(email: String) {
        val normalizedEmail = email.trim().lowercase()
        if (normalizedEmail.isBlank()) return
        val emails = (listOf(normalizedEmail) + _rememberedEmails.value.filterNot { it == normalizedEmail }).take(MAX_REMEMBERED_EMAILS)
        storage.writeRememberedEmails(emails)
        _rememberedEmails.value = emails
    }

    fun forgetEmail(email: String) {
        val emails = _rememberedEmails.value.filterNot { it == email }
        storage.writeRememberedEmails(emails)
        _rememberedEmails.value = emails
    }

    @Synchronized
    fun refresh(api: AuthApi): Boolean {
        val refreshToken = _session.value?.refreshToken ?: return false
        return try {
            val response = api.refresh(RefreshRequest(refreshToken)).execute()
            response.body()?.takeIf { response.isSuccessful }?.let {
                save(it)
                true
            } ?: run {
                clear()
                false
            }
        } catch (_: Exception) {
            false
        }
    }

    companion object {
        private const val MAX_REMEMBERED_EMAILS = 5

        fun create(context: Context) = SessionRepository(context)
    }
}

private class EncryptedSessionStorage(context: Context) {
    private val preferences = context.getSharedPreferences("authenticated_session", Context.MODE_PRIVATE)

    fun read(): AuthSession? = try {
        preferences.getString(SESSION_KEY, null)?.let(::decrypt)?.split("\n", limit = 2)?.let { parts ->
            if (parts.size == 2 && parts.all(String::isNotBlank)) AuthSession(parts[0], parts[1]) else null
        }
    } catch (_: Exception) {
        clear()
        null
    }

    fun write(session: AuthSession) {
        preferences.edit().putString(SESSION_KEY, encrypt("${session.accessToken}\n${session.refreshToken}")).apply()
    }

    fun clear() {
        preferences.edit().remove(SESSION_KEY).apply()
    }

    fun readRememberedEmails(): List<String> = try {
        preferences.getString(REMEMBERED_EMAILS_KEY, null)
            ?.let(::decrypt)
            ?.lineSequence()
            ?.map { it.trim().lowercase() }
            ?.filter(String::isNotBlank)
            ?.distinct()
            ?.toList()
            .orEmpty()
    } catch (_: Exception) {
        clearRememberedEmails()
        emptyList()
    }

    fun writeRememberedEmails(emails: List<String>) {
        preferences.edit().putString(REMEMBERED_EMAILS_KEY, encrypt(emails.joinToString("\n"))).apply()
    }

    private fun clearRememberedEmails() {
        preferences.edit().remove(REMEMBERED_EMAILS_KEY).apply()
    }

    private fun encrypt(value: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION).apply { init(Cipher.ENCRYPT_MODE, key()) }
        return Base64.encodeToString(cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP)
    }

    private fun decrypt(value: String): String {
        val bytes = Base64.decode(value, Base64.NO_WRAP)
        val cipher = Cipher.getInstance(TRANSFORMATION).apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(TAG_LENGTH_BITS, bytes.copyOfRange(0, IV_LENGTH_BYTES))) }
        return cipher.doFinal(bytes.copyOfRange(IV_LENGTH_BYTES, bytes.size)).toString(Charsets.UTF_8)
    }

    private fun key(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEY_STORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEY_STORE).apply {
            init(KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build())
        }.generateKey()
    }

    private companion object {
        const val ANDROID_KEY_STORE = "AndroidKeyStore"
        const val KEY_ALIAS = "korean_graded_reader_session"
        const val SESSION_KEY = "encrypted_tokens"
        const val REMEMBERED_EMAILS_KEY = "encrypted_remembered_emails"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val IV_LENGTH_BYTES = 12
        const val TAG_LENGTH_BITS = 128
    }
}
