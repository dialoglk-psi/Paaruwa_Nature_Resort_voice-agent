import asyncio
import logging
import os
import wave
from typing import Optional

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import JobContext, WorkerOptions, cli, AutoSubscribe
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import silero, google

load_dotenv(dotenv_path=".env")

logger = logging.getLogger("fuelpass-assistant")
logger.setLevel(logging.INFO)

GCP_PROJECT = os.getenv("GCP_PROJECT")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")  # default to us-central1

instructions_sinhala = """You are an AI assistant helping users manage their National Fuel Pass quota. This system now uses QR codes, so you can assist them with that. Please communicate exclusively in Sinhala. You should know everything about how the National Fuel Pass was built and functions.

Here is the knowledge base you must strictly follow to answer questions:

වාහන ලියාපදිංචි කිරීම – නිතර අසන ප්‍රශ්න (FAQ) 

1. වාහනය නව හිමිකරුවෙකුට මාරු වූ විට හෝ ලියාපදිංචි ජංගම දුරකථන අංකය වෙනස් වූ විට කුමක් කළ යුතුද? 
ඔබ වෙබ් අඩවිය හරහා වාහනය නැවත ලියාපදිංචි කර නව QR කේතයක් ලබාගත යුතුය. 
මෙම පහසුකම මාර්තු 16 දින අවසන් වීමෙන් (EOD) පසුව ලබා ගත හැක. 

2. නව වාහනයක් ලියාපදිංචි කරන්නේ කෙසේද? 
සියලුම නව වාහන වෙබ් අඩවිය හරහා ලියාපදිංචි කළ යුතුය. 
ලියාපදිංචි කිරීමේදී දෝෂයක් පෙනී යන අවස්ථාවක මාර්තු 16 දින අවසන් වීමෙන් (EOD) පසුව නැවත උත්සාහ කරන්න. 

3. පවතින QR කේතය භාවිතා කළ හැකිද? 
ඔව්, පවතින QR කේතය භාවිතා කර quota ලබාගත හැක. 
කෙසේ වෙතත්, ප්‍රශ්න 1 හි සඳහන් අවස්ථාවල, පවතින QR කේතය අක්‍රීය වන අතර නැවත ලියාපදිංචි කිරීමෙන් පසු නව QR කේතයක් ලබා දෙනු ඇත.
"""

instructions_tamil = """You are an AI assistant helping users manage their National Fuel Pass quota. This system now uses QR codes, so you can assist them with that. Please communicate exclusively in Tamil. You should know everything about how the National Fuel Pass was built and functions.

Here is the knowledge base you must strictly follow to answer questions:

வாகன பதிவு – அடிக்கடி கேட்கப்படும் கேள்விகள் (FAQ) 

1. என் வாகனம் புதிய உரிமையாளருக்கு மாற்றப்பட்டிருந்தால் அல்லது பதிவு செய்யப்பட்ட மொபைல் எண் மாற்றப்பட்டால் என்ன செய்ய வேண்டும்? 
நீங்கள் இணையதளம் மூலம் வாகனத்தை மீண்டும் பதிவு செய்து புதிய QR குறியீட்டை பெற வேண்டும். 
இந்த வசதி மார்ச் 16 ஆம் தேதி (நாள் முடிவிற்கு பிறகு – EOD) கிடைக்கும். 

2. புதிய வாகனத்தை எப்படி பதிவு செய்வது? 
அனைத்து புதிய வாகனங்களும் இணையதளம் மூலம் பதிவு செய்யப்பட வேண்டும். 
பதிவு செய்யும்போது பிழை ஏற்பட்டால் மார்ச் 16 ஆம் தேதி (EOD) பிறகு மீண்டும் முயற்சிக்கவும். 

3. என் தற்போதைய QR குறியீட்டை தொடர்ந்து பயன்படுத்த முடியுமா? 
ஆம், தற்போதைய QR குறியீட்டை பயன்படுத்தி quota பெறலாம். 
ஆனால் கேள்வி 1ல் குறிப்பிடப்பட்ட நிலைகளில், தற்போதைய QR குறியீடு செயலிழக்கப்படும் மற்றும் மீண்டும் பதிவு செய்த பிறகு புதிய QR குறியீடு வழங்கப்படும்.
"""


class FuelPassAgent(Agent):
    def __init__(self, language: str) -> None:
        if language == "sinhala":
            instructions = instructions_sinhala
        else:
            instructions = instructions_tamil

        super().__init__(instructions=instructions)
        self.language = language

    async def on_enter(self) -> None:
        logger.info(f"FuelPassAgent ({self.language}) activated")
        if self.language == "sinhala":
            greeting_text = "සිංහල භාෂාව තෝරාගැනීම ගැන ස්තූතියි. මම ඔබට කෙසේද උදව් කළ හැක්කේ?"
        else:
            greeting_text = "தமிழை தேர்ந்தெடுத்ததற்கு நன்றி. நான் உங்களுக்கு எவ்வாறு உதவ முடியும்?"

        await self.session.generate_reply(
            instructions=f"Your first response must be EXACTLY this phrase, word for word, with no additional text: '{greeting_text}'"
        )


async def play_greeting_wav(ctx: JobContext, file_path: str, cancel_event: asyncio.Event):
    """Play the initial greeting wav file."""
    if not os.path.exists(file_path):
        logger.warning(f"Audio file {file_path} not found. Skipping audio playback.")
        return

    try:
        wf = wave.open(file_path, 'rb')
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()

        source = rtc.AudioSource(sample_rate, channels)
        track = rtc.LocalAudioTrack.create_audio_track("greeting_wav", source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        publication = await ctx.room.local_participant.publish_track(track, options)

        chunk_length_ms = 20
        samples_per_chunk = int((sample_rate * chunk_length_ms) / 1000)

        while not cancel_event.is_set():
            data = wf.readframes(samples_per_chunk)
            if not data:
                break

            frame = rtc.AudioFrame(
                data=data,
                sample_rate=sample_rate,
                num_channels=channels,
                samples_per_channel=len(data) // (sampwidth * channels)
            )
            await source.capture_frame(frame)
            await asyncio.sleep(chunk_length_ms / 1000.0)

        await ctx.room.local_participant.unpublish_track(publication.sid)
    except Exception as e:
        logger.error(f"Failed to play greeting wav: {e}")


async def entrypoint(ctx: JobContext) -> None:
    logger.info("Initializing Fuel Pass IVR Call")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    wav_cancel_event = asyncio.Event()
    dtmf_handled_event = asyncio.Event()

    wav_path = os.path.join(os.path.dirname(__file__), "assets", "welcomeMSG.wav")

    active_session: Optional[AgentSession] = None

    async def start_agent_for_language(language: str):
        nonlocal active_session
        logger.info(f"Starting {language} agent...")
        wav_cancel_event.set()

        if not GCP_PROJECT:
            logger.error("GCP_PROJECT env var is not set. Cannot start VertexAI model.")
            return

        llm = google.beta.realtime.RealtimeModel(
            model="gemini-live-2.5-flash-native-audio",
            vertexai=True,
            project=GCP_PROJECT,
            location=GCP_LOCATION,
        )

        active_session = AgentSession(
            userdata=None,
            llm=llm,
            vad=silero.VAD.load(),
            max_tool_steps=3
        )

        agent = FuelPassAgent(language=language)

        await active_session.start(
            room=ctx.room,
            agent=agent
        )
        dtmf_handled_event.set()

    @ctx.room.on("sip_dtmf_received")
    def handle_dtmf(dtmf_event: rtc.SipDTMF):
        if dtmf_handled_event.is_set():
            return

        digit = dtmf_event.digit
        logger.info(f"Received DTMF: {digit}")

        if digit == "1":
            asyncio.create_task(start_agent_for_language("sinhala"))
        elif digit == "2":
            asyncio.create_task(start_agent_for_language("tamil"))
        else:
            logger.info("Ignoring unknown DTMF digit, waiting for 1 or 2.")

    playlist_task = asyncio.create_task(play_greeting_wav(ctx, wav_path, wav_cancel_event))

    disconnect_event = asyncio.Event()

    @ctx.room.on("disconnected")
    def on_room_disconnect(*args):
        disconnect_event.set()

    try:
        await disconnect_event.wait()
    finally:
        wav_cancel_event.set()
        if playlist_task and not playlist_task.done():
            playlist_task.cancel()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="fuel-pass-agent"
    ))