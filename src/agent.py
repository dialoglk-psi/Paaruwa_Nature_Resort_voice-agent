import asyncio
import logging
import os
import secrets
import wave
from typing import Optional

from agentmail import AgentMail
from agentmail.inboxes.types import CreateInboxRequest
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, RunContext, WorkerOptions, cli, function_tool
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import silero, google

load_dotenv(dotenv_path=".env")

logger = logging.getLogger("paaruwa-assistant")
logger.setLevel(logging.INFO)

GCP_PROJECT = os.getenv("GCP_PROJECT")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")  # default to us-central1


def _get_env(name: str) -> Optional[str]:
    val = os.getenv(name)
    if val is None:
        return None
    val = val.strip()
    return val or None


_AGENTMAIL_INBOX_ID_CACHE: Optional[str] = None


def _get_or_create_agentmail_inbox_id(
    *,
    client: AgentMail,
    username: str,
) -> str:
    """
    Return a reusable AgentMail inbox_id.

    Preference order:
    1) AGENTMAIL_INBOX_ID env var (explicit pin)
    2) in-process cache (avoid creating multiple inboxes per job/session)
    3) list existing inboxes and reuse a matching one
    4) create a new inbox (idempotent via client_id)
    """
    global _AGENTMAIL_INBOX_ID_CACHE

    pinned = _get_env("AGENTMAIL_INBOX_ID")
    if pinned:
        return pinned

    if _AGENTMAIL_INBOX_ID_CACHE:
        return _AGENTMAIL_INBOX_ID_CACHE

    # Try reusing an existing inbox first (prevents hitting inbox limits).
    try:
        res = client.inboxes.list(limit=50)
        inboxes = getattr(res, "inboxes", None) or getattr(res, "data", None) or []
        for ib in inboxes:
            if getattr(ib, "username", None) == username:
                _AGENTMAIL_INBOX_ID_CACHE = ib.inbox_id
                return ib.inbox_id
        if inboxes:
            # If username isn't available on the plan/SDK, reuse the first inbox.
            _AGENTMAIL_INBOX_ID_CACHE = inboxes[0].inbox_id
            return inboxes[0].inbox_id
    except Exception:
        # If listing fails, we'll try to create.
        pass

    inbox = client.inboxes.create(
        request=CreateInboxRequest(
            username=username,
            client_id=f"{username}-inbox",
        )
    )
    _AGENTMAIL_INBOX_ID_CACHE = inbox.inbox_id
    return inbox.inbox_id


# =============================================================================
# Knowledge bases (edit freely — swap in your real, verified prices/policies).
# Prices below marked as illustrative are taken from the property write-up you
# shared; a few gaps (e.g. banquet/day-outing exact current rates) are filled
# with clearly-labelled placeholder figures in LKR — update before going live.
# =============================================================================

instructions_sinhala = """ඔබ Paaruwa Nature Resort සඳහා පාරිභෝගික සේවා AI කථන සහායකයෙක්. ඔබ සම්පූර්ණයෙන්ම සිංහල භාෂාවෙන් පමණක් සන්නිවේදනය කළ යුතුය. Resort එක පිළිබඳ පහත දැනුම් පදනම (KB) ඔබ දැඩි ලෙස අනුගමනය කළ යුතුය.

Resort එකේ වෙබ් අඩවිය: www.paaruwa.lk

දැනුම් පදනම (KB):

1. Paaruwa Nature Resort ගැන
Paaruwa Nature Resort පිහිටා ඇත්තේ Bolgoda වැව අසබයෙහි, නාගරික ජීවිතයෙන් ඈත්ව පිහිටි සොබාදහම් පරිසරයක Piliyandala, Welmilla, Hirana පාරේය. "Experience Nature in Comfort" යන තේමාව යටතේ මංගල උත්සව, දින සංචාරක (Day Outings), ව්‍යාපාරික සම්මන්ත්‍රණ, cocktail party සහ පවුල් එකතුවීම් සඳහා පහසුකම් සපයයි.

2. කාමර සහ මිල ගණන් (LKR)
- Day-Use Room (Room only, double occupancy) – රු. 4,500 (Check-in 9pm / Check-out 5pm)
- Room Only, double occupancy – රු. 7,500
- Bed & Breakfast, double occupancy – රු. 9,000
- Half Board, double occupancy – රු. 11,000
- Full Board, double occupancy – රු. 12,500
(සාමාන්‍ය Check-in 2pm, Check-out දහවල් 12ට පෙර)
කාමරවල AC, Fan, උණුසුම් වතුර, Satellite TV, Room Service, නොමිලේ Wi-Fi ඇත.
(මෙම මිල ගණන් සාමාන්‍ය මාර්ගෝපදේශනයක් පමණි; තහවුරු කළ මිල සඳහා reservation කණ්ඩායමට යොමු කරන්න.)

3. Day Outing Package
Sunday Buffet Special Day Outing Package – රු. 1,490 (per person, ඇස්තමේන්තුගත මිලක්)
ඇතුළත්: Welcome Drink, Buffet Lunch, Changing Rooms, Outdoor Play Area, Swimming Pool, Indoor Games, Paaruwa 'Angula' Ride (request මත), Corkage Free.

4. Weddings
- Banquet Wedding – අමුත්තන් 400+ දෙනෙකු දක්වා
- Nature Wedding – විවෘත සොබාදහම් පරිසරයේ, අමුත්තන් 200+ දෙනෙකු දක්වා
- Hybrid Wedding – Banquet සහ Nature ලක්ෂණ දෙකම ඒකාබද්ධව
සම්පූර්ණ සැලසුම් හා සූදානම සඳහා කණ්ඩායම සහාය දෙනු ඇත.

5. Photoshoot Packages (ඇස්තමේන්තුගත මිල, LKR)
- Private Photoshoot – Outdoor Location රු. 10,000 / Changing Room සහිත රු. 14,000 (පැය 2)
- Corporate Photoshoot – Outdoor Location රු. 50,000 / Changing Room සහිත රු. 56,000 (පැය 12)

6. Restaurant සහ පහසුකම්
Bolgoda වැව අසබයෙහි විවෘත සංකල්පීය Restaurant එකෙන් Eastern සහ Western ආහාර සපයයි (Halal සහ Vegetarian විකල්ප ඇතුළුව). Infinity Swimming Pool, Garden, Terrace පහසුකම් ද ඇත. Free Wi-Fi, Free Parking, Room Service ලබා ගත හැක.

7. Cancellation Policy
- පැමිණීමට දින 14කට පෙර අවලංගු කිරීම – Book කළ රාත්‍රී ගාස්තුවෙන් 50%ක්
- පැමිණීමට දින 7කට පෙර අවලංගු කිරීම – Book කළ රාත්‍රී ගාස්තුවෙන් 100%ක්

8. පිහිටීම සහ දුරස්ථභාවය
Bandaranaike International Airport සිට සැතපුම් 34ක් පමණ; Mount Lavinia Bus Stand සැතපුම් 11ක් පමණ; Barefoot Gallery සැතපුම් 14ක් පමණ. Ratmalana Airport සැතපුම් 14ක් පමණ. Panadura Railway Station කි.මී. 7ක් පමණ.

9. සම්බන්ධ වීමට
දුරකථන: 0702988488 | 0382288488 | 0774188488
විද්‍යුත් තැපෑල: info@paaruwa.lk
ලිපිනය: 286, Hirana Road, Kindelpitiya, Welmilla, Piliyandala 12534, Sri Lanka

10. ගෙවීම් (Bank Deposit)
Bank: Sampath Bank, Branch: Maharagama
Account Name: Paaruwa
Account Number: 101314002473
(ගෙවීම් සිදු කරන්නේ නම් ලද පසු resort කණ්ඩායමට තහවුරු කිරීම සඳහා ඇමතුමක් හෝ email එකක් යැවීමට යෝජනා කරන්න.)

TOOL USE POLICY (IMPORTANT):
- ඔබ ඉහත KB එක පමණක් ඇසුරෙන් පිළිතුරු දිය යුතුය.
- Caller ගේ ප්‍රශ්නය KB එකෙන් පිළිතුරු දිය නොහැකි නම්, හෝ නිශ්චිත වෙන්කරවා ගැනීමක් (booking) සිදු කිරීමට අවශ්‍ය නම්, ඔබ:
  1) `support_ticket` tool එක, ප්‍රශ්නයේ කෙටි සිංහල සාරාංශයක් (වාක්‍ය 1-2) සමඟ call කරන්න.
  2) පසුව caller ට හරියටම මෙම වාක්‍යය පවසන්න (වෙනත් text නොමැතිව): "ඔබගේ ඉල්ලීමට පිළිතුරු දීමට දැනට තොරතුරු නොමැති බැවින්, මම ඔබ වෙනුවෙන් ඉල්ලීමක් ලියාපදිංචි කර ඇත. අපගේ කණ්ඩායම ඉක්මනින් ඔබට නැවත සම්බන්ධ වනු ඇත."
- Resort සම්බන්ධ නොවන මාතෘකා සඳහා tool එක භාවිතා නොකරන්න.
"""

instructions_english = """You are an AI customer-service voice assistant for Paaruwa Nature Resort. Please communicate exclusively in English. You must strictly follow the knowledge base (KB) below about the resort.

Resort website: www.paaruwa.lk

KNOWLEDGE BASE (KB):

1. About Paaruwa Nature Resort
Paaruwa Nature Resort is set on the bank of Bolgoda Lake, in a village isolated from urban life, in Piliyandala (Welmilla, Hirana Road). Under the theme "Experience Nature in Comfort," it caters to weddings, day outings, business conferences, outbound training, cocktail parties, and family get-togethers.

2. Rooms & Rates (LKR)
- Day-Use Room (room only, double occupancy) – LKR 4,500 (Check-in 9pm / Check-out 5pm)
- Room only, double occupancy – LKR 7,500
- Bed & Breakfast, double occupancy – LKR 9,000
- Half Board, double occupancy – LKR 11,000
- Full Board, double occupancy – LKR 12,500
(Standard check-in 2pm, check-out before 12 noon)
Rooms include AC, fan, hot water, satellite TV, room service, and free Wi-Fi.
(These rates are a general guide only; confirm exact current pricing with the reservations team.)

3. Day Outing Package
Sunday Buffet Special Day Outing Package – LKR 1,490 (per person, indicative price)
Includes: welcome drink, buffet lunch, changing rooms, outdoor play area, swimming pool, indoor games, Paaruwa "Angula" ride (on request), corkage free.

4. Weddings
- Banquet Wedding – up to 400+ guests
- Nature Wedding – open-concept, lakeside, up to 200+ guests
- Hybrid Wedding – combines banquet and nature wedding features
The team supports planning from start to finish.

5. Photoshoot Packages (indicative rates, LKR)
- Private Photoshoot – Outdoor location LKR 10,000 / with changing room LKR 14,000 (2 hours)
- Corporate Photoshoot – Outdoor location LKR 50,000 / with changing room LKR 56,000 (12 hours)

6. Restaurant & Facilities
An open-concept restaurant on the lake front serves Eastern and Western dishes (including halal and vegetarian options). The resort also has an infinity swimming pool, garden, and terrace. Free Wi-Fi, free parking, and room service are available.

7. Cancellation Policy
- Cancellations within 14 days of arrival – 50% of booked room nights charged
- Cancellations within 7 days of arrival – 100% of booked room nights charged

8. Location & Distances
About 34 miles from Bandaranaike International Airport; about 11 miles from Mount Lavinia Bus Stand; about 14 miles from Barefoot Gallery; about 14 miles from Ratmalana Airport; about 7 km from Panadura Railway Station.

9. Contact
Phone: 0702988488 | 0382288488 | 0774188488
Email: info@paaruwa.lk
Address: 286, Hirana Road, Kindelpitiya, Welmilla, Piliyandala 12534, Sri Lanka

10. Payment (Bank Deposit)
Bank: Sampath Bank, Branch: Maharagama
Account Name: Paaruwa
Account Number: 101314002473
(If a caller makes a deposit, suggest they call or email to confirm the payment with the resort team.)

TOOL USE POLICY (IMPORTANT):
- You must answer strictly using ONLY the KB above.
- If the caller's question is not covered by the KB, or requires an actual booking/reservation, you MUST:
  1) Call the tool `support_ticket` with a short English summary of the request (1-2 sentences).
  2) Then reply to the caller with EXACTLY this sentence (no extra text): "I don't have that information right now, so I've logged a request for you. Our team will get back to you shortly."
- Do NOT use the tool for topics unrelated to the resort.
"""

instructions_tamil = """நீங்கள் Paaruwa Nature Resort நிறுவனத்திற்கான வாடிக்கையாளர் சேவை AI குரல் உதவியாளர். தயவுசெய்து முழுவதுமாக தமிழ் மொழியில் மட்டும் தொடர்பு கொள்ளுங்கள். கீழே கொடுக்கப்பட்டுள்ள தகவல் தளத்தை (KB) மட்டுமே கண்டிப்பாகப் பின்பற்ற வேண்டும்.

Resort இணையதளம்: www.paaruwa.lk

தகவல் தளம் (KB):

1. Paaruwa Nature Resort பற்றி
Paaruwa Nature Resort, நகர்ப்புற வாழ்க்கையிலிருந்து விலகிய ஒரு கிராமத்தில், Bolgoda ஏரிக்கரையில், Piliyandala (Welmilla, Hirana Road) அமைந்துள்ளது. "Experience Nature in Comfort" என்ற கருப்பொருளின் கீழ், திருமணங்கள், Day Outings, வணிக மாநாடுகள், Outbound Training, Cocktail Party, குடும்ப சந்திப்புகள் ஆகியவற்றிற்கு வசதிகள் வழங்குகிறது.

2. அறைகள் மற்றும் விலைகள் (LKR)
- Day-Use Room (Room only, double occupancy) – ரூ. 4,500 (Check-in 9pm / Check-out 5pm)
- Room Only, double occupancy – ரூ. 7,500
- Bed & Breakfast, double occupancy – ரூ. 9,000
- Half Board, double occupancy – ரூ. 11,000
- Full Board, double occupancy – ரூ. 12,500
(வழக்கமான Check-in 2pm, Check-out மதியம் 12க்கு முன்)
அறைகளில் AC, Fan, சூடான நீர், Satellite TV, Room Service, இலவச Wi-Fi உள்ளது.
(இந்த விலைகள் பொது வழிகாட்டி மட்டுமே; உறுதிப்படுத்தப்பட்ட விலைக்கு reservation குழுவை தொடர்பு கொள்ளவும்.)

3. Day Outing Package
Sunday Buffet Special Day Outing Package – ரூ. 1,490 (ஒரு நபருக்கு, மதிப்பீட்டு விலை)
சேர்க்கப்பட்டவை: Welcome Drink, Buffet Lunch, Changing Rooms, Outdoor Play Area, Swimming Pool, Indoor Games, Paaruwa 'Angula' Ride (கோரிக்கையின் பேரில்), Corkage Free.

4. திருமணங்கள்
- Banquet Wedding – 400+ விருந்தினர்கள் வரை
- Nature Wedding – திறந்த வெளியில், ஏரிக்கரையில், 200+ விருந்தினர்கள் வரை
- Hybrid Wedding – Banquet மற்றும் Nature Wedding இரண்டின் அம்சங்களும் இணைந்தது
திட்டமிடல் முதல் இறுதி வரை குழு உதவி வழங்கும்.

5. Photoshoot Packages (மதிப்பீட்டு விலைகள், LKR)
- Private Photoshoot – Outdoor Location ரூ. 10,000 / Changing Room உடன் ரூ. 14,000 (2 மணி நேரம்)
- Corporate Photoshoot – Outdoor Location ரூ. 50,000 / Changing Room உடன் ரூ. 56,000 (12 மணி நேரம்)

6. Restaurant மற்றும் வசதிகள்
ஏரிக்கரையில் அமைந்த திறந்த கருத்தமைவு கொண்ட Restaurant, Eastern மற்றும் Western உணவுகளை வழங்குகிறது (Halal மற்றும் Vegetarian விருப்பங்கள் உட்பட). Infinity Swimming Pool, Garden, Terrace வசதிகளும் உள்ளன. இலவச Wi-Fi, இலவச Parking, Room Service கிடைக்கும்.

7. Cancellation Policy
- வருகைக்கு 14 நாட்களுக்குள் ரத்து செய்தால் – Book செய்த அறை இரவுகளில் 50% கட்டணம்
- வருகைக்கு 7 நாட்களுக்குள் ரத்து செய்தால் – Book செய்த அறை இரவுகளில் 100% கட்டணம்

8. இருப்பிடம் மற்றும் தூரம்
Bandaranaike International Airport இலிருந்து சுமார் 34 மைல்கள்; Mount Lavinia Bus Stand சுமார் 11 மைல்கள்; Barefoot Gallery சுமார் 14 மைல்கள்; Ratmalana Airport சுமார் 14 மைல்கள்; Panadura Railway Station சுமார் 7 கி.மீ.

9. தொடர்பு கொள்ள
தொலைபேசி: 0702988488 | 0382288488 | 0774188488
மின்னஞ்சல்: info@paaruwa.lk
முகவரி: 286, Hirana Road, Kindelpitiya, Welmilla, Piliyandala 12534, Sri Lanka

10. கட்டணம் (Bank Deposit)
Bank: Sampath Bank, Branch: Maharagama
Account Name: Paaruwa
Account Number: 101314002473
(வைப்பு செலுத்தினால், resort குழுவுடன் உறுதிப்படுத்த அழைக்கவும் அல்லது மின்னஞ்சல் அனுப்பவும் பரிந்துரைக்கவும்.)

TOOL USE POLICY (IMPORTANT):
- நீங்கள் மேலே உள்ள KB ஐ மட்டுமே பயன்படுத்தி பதிலளிக்க வேண்டும்.
- Caller இன் கேள்விக்கு KB இல் பதில் இல்லை என்றால், அல்லது உண்மையான booking தேவைப்பட்டால், நீங்கள்:
  1) `support_ticket` tool ஐ, கேள்வியின் சுருக்கமான தமிழ் சுருக்கத்துடன் (1-2 வாக்கியங்கள்) call செய்யவும்.
  2) பின்னர் caller க்கு சரியாக இந்த வாக்கியத்தை மட்டும் சொல்லவும் (கூடுதல் உரை இல்லாமல்): "உங்கள் கோரிக்கைக்கு பதிலளிக்க தற்போது தேவையான தகவல்கள் இல்லை. நான் உங்களுக்காக ஒரு கோரிக்கையை பதிவு செய்துள்ளேன். எங்கள் குழு விரைவில் உங்களை தொடர்பு கொள்ளும்."
- Resort தொடர்பில்லாத தலைப்புகளுக்கு இந்த tool ஐ பயன்படுத்த வேண்டாம்.
"""


class ResortAgent(Agent):
    def __init__(self, language: str) -> None:
        if language == "sinhala":
            instructions = instructions_sinhala
        elif language == "tamil":
            instructions = instructions_tamil
        else:
            instructions = instructions_english

        super().__init__(instructions=instructions)
        self.language = language

    @function_tool(name="support_ticket")
    async def support_ticket(
        self,
        context: RunContext,
        question_summary: str,
        caller_phone: Optional[str] = None,
    ) -> dict:
        """Log a support/booking request by emailing the reservations team.

        Subject must be "resort-request ####" (unique 4 digits). Body must include
        the caller's phone number (if known) and a summary of what they need.
        """
        api_key = _get_env("AGENTMAIL_API_KEY")
        username = _get_env("AGENTMAIL_USERNAME")
        to_email = _get_env("AGENTMAIL_TO_EMAIL")

        missing = [
            name
            for name, val in (
                ("AGENTMAIL_API_KEY", api_key),
                ("AGENTMAIL_USERNAME", username),
                ("AGENTMAIL_TO_EMAIL", to_email),
            )
            if not val
        ]
        if missing:
            logger.error(
                "AgentMail env vars missing: %s",
                ", ".join(missing),
            )
            return {"ok": False, "error": "agentmail_not_configured", "missing": missing}

        inferred_phone = None
        try:
            userdata = getattr(context, "userdata", None)
            if isinstance(userdata, dict):
                inferred_phone = userdata.get("caller_phone")
        except Exception:
            inferred_phone = None

        phone = caller_phone or inferred_phone or "unknown"
        ticket_num = secrets.randbelow(10000)

        subject = f"resort-request {ticket_num:04d}"
        body = f"Caller phone: {phone}\n\nRequest summary:\n{question_summary}\n"

        try:
            client = AgentMail(api_key=api_key)

            inbox_id = _get_or_create_agentmail_inbox_id(client=client, username=username)

            client.inboxes.messages.send(
                inbox_id,
                to=to_email,
                subject=subject,
                text=body,
            )

            logger.info(f"Sent support request via AgentMail: {subject}")
            return {"ok": True, "ticket": f"{ticket_num:04d}"}
        except Exception as e:
            logger.exception(f"Failed to send AgentMail email: {e}")
            return {"ok": False, "error": str(e)}

    async def on_enter(self) -> None:
        logger.info(f"ResortAgent ({self.language}) activated")
        if self.language == "sinhala":
            greeting_text = "සිංහල භාෂාව තෝරාගැනීම ගැන ස්තූතියි. Paaruwa Nature Resort වෙත සාදරයෙන් පිළිගනිමු. මම ඔබට කෙසේද උදව් කළ හැක්කේ?"
        elif self.language == "tamil":
            greeting_text = "தமிழை தேர்ந்தெடுத்ததற்கு நன்றி. Paaruwa Nature Resort-க்கு உங்களை வரவேற்கிறோம். நான் உங்களுக்கு எவ்வாறு உதவ முடியும்?"
        else:
            greeting_text = "Thank you for choosing English. Welcome to Paaruwa Nature Resort. How can I help you today?"

        await self.session.generate_reply(
            instructions=f"Your first response must be EXACTLY this phrase, word for word, with no additional text: '{greeting_text}'"
        )


async def play_greeting_wav(ctx: JobContext, file_path: str, cancel_event: asyncio.Event):
    """Play the initial greeting wav file (e.g. language menu prompt)."""
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
    logger.info("Initializing Paaruwa Nature Resort IVR Call")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    wav_cancel_event = asyncio.Event()
    dtmf_handled_event = asyncio.Event()

    # Greeting wav should say e.g.:
    # "Welcome to Paaruwa Nature Resort. For Sinhala press 1, for English press 2, for Tamil press 3."
    wav_path = os.path.join(os.path.dirname(__file__), "assets", "welcomeMSG.wav")

    active_session: Optional[AgentSession] = None

    def _infer_caller_phone() -> Optional[str]:
        # Best-effort: SIP gateways often store caller ID in participant identity or attributes.
        try:
            for p in ctx.room.remote_participants.values():
                attrs = getattr(p, "attributes", None) or {}
                for key in (
                    "sip.phoneNumber",
                    "sip.phone_number",
                    "sip.from",
                    "sip.caller_id",
                    "phone",
                    "phone_number",
                ):
                    val = attrs.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()

                ident = getattr(p, "identity", None)
                if isinstance(ident, str) and ident.strip():
                    return ident.strip()
        except Exception:
            return None
        return None

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

        caller_phone = _infer_caller_phone()
        active_session = AgentSession(
            userdata={"caller_phone": caller_phone} if caller_phone else {},
            llm=llm,
            vad=silero.VAD.load(),
            max_tool_steps=3
        )

        agent = ResortAgent(language=language)

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
            asyncio.create_task(start_agent_for_language("english"))
        elif digit == "3":
            asyncio.create_task(start_agent_for_language("tamil"))
        else:
            logger.info("Ignoring unknown DTMF digit, waiting for 1, 2 or 3.")

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
        agent_name="paaruwa-resort-agent"
    ))