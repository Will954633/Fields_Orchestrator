package au.com.fieldsestate.voiceagent

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.media.MediaPlayer
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.util.Base64
import android.util.Log
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import au.com.fieldsestate.voiceagent.databinding.ActivityMainBinding
import java.io.File
import java.io.FileOutputStream

class MainActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "MainActivity"
    }

    private lateinit var binding: ActivityMainBinding
    private lateinit var recorder: AudioRecorder
    private lateinit var apiClient: ApiClient
    private var mediaPlayer: MediaPlayer? = null

    private var isRecording = false
    private var isBusy = false

    // Permission launcher
    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            setStatus("Ready. Tap and hold to speak.")
        } else {
            setStatus("Microphone permission required")
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Init components
        recorder = AudioRecorder(this)
        apiClient = ApiClient(
            baseUrl = BuildConfig.API_BASE_URL,
            token = BuildConfig.API_TOKEN,
        )

        // Request mic permission
        if (!recorder.hasPermission()) {
            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }

        // Set model label
        binding.modelLabel.text = "Claude Opus · Fields Agent"

        // Push-to-talk button
        binding.pushToTalkButton.setOnTouchListener { view, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    if (!isBusy) startRecording(view)
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if (isRecording) stopRecordingAndSend()
                    true
                }
                else -> false
            }
        }

        // Health check on start
        apiClient.healthCheck { ok, msg ->
            runOnUiThread {
                if (ok) {
                    setStatus("Connected. Tap and hold to speak.")
                } else {
                    setStatus("Cannot reach server — check connection")
                    Log.w(TAG, "Health check failed: $msg")
                }
            }
        }
    }

    private fun startRecording(view: View) {
        if (!recorder.hasPermission()) {
            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            return
        }

        val started = recorder.startRecording()
        if (!started) {
            setStatus("Failed to start recording")
            return
        }

        isRecording = true
        vibrate()

        // Visual feedback
        binding.pushToTalkButton.backgroundTintList =
            ContextCompat.getColorStateList(this, R.color.recording_red)
        setStatus("Listening...")
    }

    private fun stopRecordingAndSend() {
        isRecording = false
        isBusy = true

        // Visual feedback
        binding.pushToTalkButton.backgroundTintList =
            ContextCompat.getColorStateList(this, R.color.fields_blue)
        setStatus("Processing...")
        vibrate()

        val audioBytes = recorder.stopRecording()

        if (audioBytes.size < 1000) {
            // Too short — probably just a tap
            setStatus("Hold the button longer to record")
            isBusy = false
            return
        }

        apiClient.sendVoice(audioBytes, "work",
            onResult = { response ->
                runOnUiThread {
                    // Show transcript
                    if (response.transcript.isNotBlank()) {
                        addChatBubble(response.transcript, isUser = true)
                    }

                    // Show reply
                    if (response.reply.isNotBlank()) {
                        addChatBubble(response.reply, isUser = false)
                    }

                    // Play audio
                    if (!response.audioBase64.isNullOrBlank()) {
                        playAudioBase64(response.audioBase64, response.audioFormat ?: "mp3")
                    }

                    setStatus("Tap and hold to speak")
                    isBusy = false
                }
            },
            onError = { error ->
                runOnUiThread {
                    setStatus("Error: $error")
                    addChatBubble("Error: $error", isUser = false)
                    isBusy = false
                }
            }
        )
    }

    private fun addChatBubble(text: String, isUser: Boolean) {
        val tv = TextView(this).apply {
            this.text = text
            setTextColor(ContextCompat.getColor(context, R.color.text_primary))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            setPadding(dp(16), dp(12), dp(16), dp(12))

            val bgColor = if (isUser) R.color.user_bubble else R.color.agent_bubble
            setBackgroundColor(ContextCompat.getColor(context, bgColor))

            val params = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            params.setMargins(
                if (isUser) dp(48) else 0,
                dp(4),
                if (isUser) 0 else dp(48),
                dp(4)
            )
            layoutParams = params
            gravity = if (isUser) Gravity.END else Gravity.START
        }

        // Add label
        val label = TextView(this).apply {
            this.text = if (isUser) "You" else "Claude"
            setTextColor(ContextCompat.getColor(context, R.color.text_secondary))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 11f)
            setPadding(dp(4), dp(8), dp(4), dp(0))
            val params = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            params.gravity = if (isUser) Gravity.END else Gravity.START
            layoutParams = params
        }

        binding.chatContainer.addView(label)
        binding.chatContainer.addView(tv)

        // Scroll to bottom
        binding.scrollView.post {
            binding.scrollView.fullScroll(ScrollView.FOCUS_DOWN)
        }
    }

    private fun playAudioBase64(base64Audio: String, format: String) {
        try {
            val audioBytes = Base64.decode(base64Audio, Base64.DEFAULT)
            val tmpFile = File.createTempFile("tts_", ".$format", cacheDir)
            FileOutputStream(tmpFile).use { it.write(audioBytes) }

            mediaPlayer?.release()
            mediaPlayer = MediaPlayer().apply {
                setDataSource(tmpFile.absolutePath)
                setOnCompletionListener {
                    it.release()
                    tmpFile.delete()
                }
                prepare()
                start()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Audio playback failed", e)
        }
    }

    private fun setStatus(text: String) {
        binding.statusText.text = text
    }

    private fun vibrate() {
        val vibrator = getSystemService(Vibrator::class.java) ?: return
        vibrator.vibrate(VibrationEffect.createOneShot(50, VibrationEffect.DEFAULT_AMPLITUDE))
    }

    private fun dp(value: Int): Int {
        return TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP,
            value.toFloat(),
            resources.displayMetrics
        ).toInt()
    }

    override fun onDestroy() {
        super.onDestroy()
        mediaPlayer?.release()
    }
}
