package au.com.fieldsestate.voiceagent

import android.util.Log
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * HTTP client for the Fields Voice Agent backend API.
 */
class ApiClient(
    private val baseUrl: String,
    private val token: String = ""
) {
    companion object {
        private const val TAG = "ApiClient"
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)  // Claude can take time
        .build()

    data class VoiceResponse(
        val transcript: String,
        val reply: String,
        val audioBase64: String?,
        val audioFormat: String?,
        val mode: String,
        val error: String? = null,
    )

    /**
     * Send recorded audio to the backend and get a response.
     */
    fun sendVoice(
        audioBytes: ByteArray,
        mode: String,
        onResult: (VoiceResponse) -> Unit,
        onError: (String) -> Unit
    ) {
        val audioBody = audioBytes.toRequestBody("audio/wav".toMediaType())

        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("audio", "recording.wav", audioBody)
            .addFormDataPart("mode", mode)
            .build()

        val request = Request.Builder()
            .url("$baseUrl/api/voice")
            .apply {
                if (token.isNotBlank()) {
                    addHeader("Authorization", "Bearer $token")
                }
            }
            .post(body)
            .build()

        Log.i(TAG, "Sending ${audioBytes.size} bytes to $baseUrl/api/voice (mode=$mode)")

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e(TAG, "Request failed", e)
                onError("Connection failed: ${e.message}")
            }

            override fun onResponse(call: Call, response: Response) {
                val bodyStr = response.body?.string() ?: ""
                if (!response.isSuccessful) {
                    Log.e(TAG, "HTTP ${response.code}: $bodyStr")
                    onError("Server error (${response.code})")
                    return
                }

                try {
                    val json = JSONObject(bodyStr)
                    if (json.has("error")) {
                        onError(json.getString("error"))
                        return
                    }
                    onResult(VoiceResponse(
                        transcript = json.optString("transcript", ""),
                        reply = json.optString("reply", ""),
                        audioBase64 = json.optString("audio_base64", null),
                        audioFormat = json.optString("audio_format", "mp3"),
                        mode = json.optString("mode", mode),
                    ))
                } catch (e: Exception) {
                    Log.e(TAG, "Parse error", e)
                    onError("Failed to parse response")
                }
            }
        })
    }

    /**
     * Send text (for testing without microphone).
     */
    fun sendText(
        text: String,
        mode: String,
        onResult: (String) -> Unit,
        onError: (String) -> Unit
    ) {
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("text", text)
            .addFormDataPart("mode", mode)
            .build()

        val request = Request.Builder()
            .url("$baseUrl/api/chat")
            .apply {
                if (token.isNotBlank()) {
                    addHeader("Authorization", "Bearer $token")
                }
            }
            .post(body)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                onError("Connection failed: ${e.message}")
            }

            override fun onResponse(call: Call, response: Response) {
                val bodyStr = response.body?.string() ?: ""
                if (!response.isSuccessful) {
                    onError("Server error (${response.code})")
                    return
                }
                try {
                    val json = JSONObject(bodyStr)
                    onResult(json.optString("reply", ""))
                } catch (e: Exception) {
                    onError("Failed to parse response")
                }
            }
        })
    }

    /**
     * Health check.
     */
    fun healthCheck(onResult: (Boolean, String) -> Unit) {
        val request = Request.Builder()
            .url("$baseUrl/api/health")
            .get()
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                onResult(false, "Cannot reach server: ${e.message}")
            }

            override fun onResponse(call: Call, response: Response) {
                onResult(response.isSuccessful, response.body?.string() ?: "")
            }
        })
    }
}
