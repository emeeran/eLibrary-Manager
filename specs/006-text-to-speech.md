# SPEC-006: Text-to-Speech

- **Status:** Active
- **Version:** 1.0.0
- **Last Updated:** 2026-04-15

## Purpose

Provides read-aloud functionality for ebook content using multiple TTS engines with automatic fallback. Supports voice selection, rate/pitch adjustment, and client/server hybrid architecture where EdgeTTS and gTTS run server-side while Browser Speech API runs client-side.

---

## Behavior

### Engine Listing

#### AC-006.01: List TTS Engines
**Given** the application is running
**When** the user requests `GET /api/tts/engines`
**Then** the system returns a list of 3 engines: `edgetts`, `browser`, `gtts`
**And** each engine includes `id`, `name`, `description`, and `is_server` (boolean)
**And** `default_engine` is `edgetts`
**And** `fallback_order` is `[edgetts, browser, gtts]`

#### AC-006.02: Engine Metadata
**Given** the engine list response
**When** examining engine properties
**Then** EdgeTTS has `is_server: true`, name "EdgeTTS (Neural)", description "High-quality neural voices from Microsoft Edge"
**And** Browser has `is_server: false`, name "Browser Speech", description "Built-in browser text-to-speech"
**And** gTTS has `is_server: true`, name "Google TTS", description "Basic text-to-speech from Google"

---

### Voice Enumeration

#### AC-006.03: List EdgeTTS Voices
**Given** EdgeTTS service is available
**When** the user requests `GET /api/tts/voices?engine=edgetts`
**Then** the system returns available neural voices from EdgeTTS
**And** includes `engine: "edgetts"`, `voices: [...]`, and `default_voice`

#### AC-006.04: List gTTS Voices
**Given** gTTS service is available
**When** the user requests `GET /api/tts/voices?engine=gtts`
**Then** the system returns available language codes for gTTS
**And** includes `engine: "gtts"`, `voices: [...]`, and `default_voice`

#### AC-006.05: List Browser Voices
**Given** any request context
**When** the user requests `GET /api/tts/voices?engine=browser`
**Then** the system returns `{ engine: "browser", voices: [], default_voice: null, note: "Browser voices are loaded client-side" }`
**And** the frontend JS populates voices from `window.speechSynthesis.getVoices()`

#### AC-006.06: Default Engine Voices
**Given** no engine parameter is provided
**When** the user requests `GET /api/tts/voices`
**Then** the system defaults to `engine=edgetts`
**And** returns EdgeTTS voices

---

### Speech Synthesis

#### AC-006.07: Synthesize with EdgeTTS
**Given** EdgeTTS service is available
**When** the user posts `POST /api/tts/synthesize` with `{ text, voice, rate, pitch, engine: "edgetts" }`
**Then** the system generates MP3 audio via EdgeTTS neural engine
**And** returns `audio/mpeg` response with `Content-Disposition: attachment; filename=speech_edgetts.mp3`
**And** includes `X-TTS-Engine: edgetts` header
**And** includes `Cache-Control: no-cache` header

#### AC-006.08: Synthesize with gTTS
**Given** gTTS service is available
**When** the user posts `POST /api/tts/synthesize` with `{ text, voice, rate, pitch, engine: "gtts" }`
**Then** the system generates MP3 audio via gTTS
**And** returns `audio/mpeg` response with `X-TTS-Engine: gtts` header

#### AC-006.09: Browser Engine Rejection
**Given** a client requests server-side synthesis
**When** the user posts `POST /api/tts/synthesize` with `{ engine: "browser" }`
**Then** the system returns HTTP 400 with detail "Browser TTS is handled client-side. Use Web Speech API directly."

#### AC-006.10: Unknown Engine Rejection
**Given** a client provides an unrecognized engine
**When** the user posts `POST /api/tts/synthesize` with `{ engine: "unknown" }`
**Then** the system returns HTTP 400 with detail "Unknown engine: unknown"

#### AC-006.11: Missing Text Rejection
**Given** a client omits the text field
**When** the user posts `POST /api/tts/synthesize` with `{ engine: "edgetts" }`
**Then** the system returns HTTP 400 with detail "text field is required"

#### AC-006.12: Empty Text Rejection
**Given** a client provides an empty text string
**When** the user posts `POST /api/tts/synthesize` with `{ text: "", engine: "edgetts" }`
**Then** the system returns HTTP 400 with detail "text field is required"

#### AC-006.13: Default Engine Fallback
**Given** no engine parameter is provided
**When** the user posts `POST /api/tts/synthesize` with `{ text, voice }`
**Then** the system defaults to `engine=edgetts`

---

### Fallback Behavior

#### AC-006.14: EdgeTTS to gTTS Fallback
**Given** EdgeTTS service fails (raises EdgeTTSError or unexpected exception)
**When** synthesis is attempted with `engine=edgetts`
**Then** the system logs a warning "EdgeTTS failed, falling back to gTTS"
**And** attempts synthesis with gTTS
**And** returns audio with `X-TTS-Engine: gtts` header

#### AC-006.15: Complete Synthesis Failure
**Given** both EdgeTTS and gTTS fail
**When** synthesis is attempted
**Then** the system returns HTTP 500 with `{ error: "Synthesis failed", message: <error>, details: <details> }`

---

### Rate and Pitch Parameters

#### AC-006.16: Rate Normalization
**Given** a non-numeric rate value is provided
**When** the user posts `{ text, rate: "fast" }`
**Then** the system normalizes rate to `1.0` (default)

#### AC-006.17: Valid Rate Range
**Given** a valid rate value
**When** the user posts `{ text, rate: 1.5 }`
**Then** the system uses the provided rate for synthesis
**And** the settings UI supports: 0.5, 0.75, 1.0, 1.25, 1.5, 2.0

#### AC-006.18: Pitch Control
**Given** a pitch adjustment string
**When** the user posts `{ text, pitch: "+50Hz" }`
**Then** the system applies the pitch shift to EdgeTTS synthesis
**And** the settings UI supports float range 0.5 to 2.0

---

### Frontend Playback Controls

#### AC-006.19: Play/Pause/Stop Controls
**Given** a reader view is loaded with TTS enabled
**When** the user clicks play
**Then** the system sends the selected text/chapter to the synthesize endpoint
**And** plays the returned MP3 audio via the browser's Audio API
**And** toggles the button to pause

#### AC-006.20: Text Highlighting
**Given** TTS is actively reading
**When** audio playback progresses
**Then** the frontend highlights the word/phrase currently being spoken
**And** scrolls the view to keep highlighted text visible

#### AC-006.21: Voice Selection
**Given** the TTS panel is open
**When** the user selects a voice from the dropdown
**Then** the system uses the selected voice for subsequent synthesis
**And** the dropdown is populated from `/api/tts/voices`

#### AC-006.22: Speed/Pitch Sliders
**Given** the TTS panel is open
**When** the user adjusts the speed or pitch slider
**Then** the rate/pitch parameters update in real-time
**And** subsequent synthesis uses the updated values

#### AC-006.23: Browser TTS Client-Side Fallback
**Given** server-side TTS is unavailable
**When** the user triggers read-aloud with browser engine selected
**Then** the frontend uses the Web Speech API (`window.speechSynthesis`)
**And** voices are loaded from `window.speechSynthesis.getVoices()`
**And** rate/pitch are applied via `SpeechSynthesisUtterance` properties

---

## API Contract

### Endpoints

| Method | Path | Request | Response | Status Codes |
|--------|------|---------|----------|-------------|
| GET | `/api/tts/engines` | — | `{ engines: [...], default_engine, fallback_order }` | 200 |
| GET | `/api/tts/voices` | Query: `engine` (string, default: `edgetts`) | `{ engine, voices: [...], default_voice }` | 200 |
| POST | `/api/tts/synthesize` | JSON: `{ text, voice?, rate?, pitch?, engine? }` | `audio/mpeg` binary with `X-TTS-Engine` header | 200, 400, 500 |

### Synthesize Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `text` | string | Yes | — | Text content to synthesize |
| `voice` | string | No | `"en"` | Voice ID or language code |
| `rate` | float | No | `1.0` | Playback rate (0.5–2.0) |
| `pitch` | string | No | `"+0Hz"` | Pitch adjustment for EdgeTTS |
| `engine` | string | No | `"edgetts"` | TTS engine: `edgetts`, `browser`, `gtts` |

### Engine Object

```json
{
  "id": "edgetts",
  "name": "EdgeTTS (Neural)",
  "description": "High-quality neural voices from Microsoft Edge",
  "is_server": true
}
```

### Audio Response Headers

| Header | Value |
|--------|-------|
| `Content-Type` | `audio/mpeg` |
| `Content-Disposition` | `attachment; filename=speech_{engine}.mp3` |
| `Cache-Control` | `no-cache` |
| `X-TTS-Engine` | Engine ID used for synthesis |

---

## Implementation Map

| Component | File | Key Functions |
|-----------|------|---------------|
| Routes | `app/routes/ai_tts.py` | `get_tts_engines`, `get_tts_voices`, `synthesize_speech`, `_audio_response` |
| EdgeTTS Service | `app/edgetts_service.py` | `EdgeTTSService.generate_audio`, `get_voices`, `get_default_voice` |
| gTTS Service | `app/gtts_service.py` | `GTTSService.text_to_speech`, `get_voices`, `get_default_voice` |
| Frontend | `app/static/js/tts.js` | TTS controller, play/pause/stop, highlighting, voice dropdown |
| Settings | `app/routes/settings.py` | `tts_speed`, `tts_pitch` config |
| Constants | `app/routes/ai_tts.py` | `ENGINE_EDGETTS`, `ENGINE_BROWSER`, `ENGINE_GTTS` |

---

## Test Coverage

| Spec Requirement | Test File | Test Function | Status |
|------------------|-----------|---------------|--------|
| AI providers endpoint | tests/test_api.py | test_ai_providers_endpoint | Covered |
| AI provider active | tests/test_api.py | test_ai_provider_active_endpoint | Covered |
| List TTS engines | — | — | GAP |
| List TTS voices | — | — | GAP |
| Synthesize with EdgeTTS | — | — | GAP |
| Synthesize with gTTS | — | — | GAP |
| Browser engine rejection | — | — | GAP |
| Unknown engine rejection | — | — | GAP |
| Missing text rejection | — | — | GAP |
| EdgeTTS to gTTS fallback | — | — | GAP |
| Complete synthesis failure | — | — | GAP |
| Rate normalization | — | — | GAP |
| Frontend playback controls | — | — | GAP |
| Text highlighting | — | — | GAP |
| Voice selection | — | — | GAP |
| Speed/pitch sliders | — | — | GAP |
| Browser TTS client-side | — | — | GAP |

---

## Dependencies

- **SPEC-002:** Reader Interface (reading context, chapter content)
- **SPEC-007:** Settings (TTS speed/pitch configuration)
- **External:** edge-tts (Python package), gTTS (Python package)
- **Browser APIs:** Web Speech API (`window.speechSynthesis`, `SpeechSynthesisUtterance`)

---

## Open Questions

- None
