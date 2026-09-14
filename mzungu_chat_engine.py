"""
mzungu_chat_engine.py — ChatPay Foreign Partner Conversation Engine
=========================================================================
A fully context-aware, multi-turn conversation engine that:
  1. Selects a prompt from 1,000 rotational questions (per-user or global)
  2. Builds a non-repetitive, natural intro so teachers never see the same greeting
  3. Reacts intelligently to WHAT THE TEACHER ACTUALLY SAID — vocabulary corrections,
     verb conjugations, directions, shopping tips — and continues a flowing dialogue
  4. Tracks conversation turns so responses escalate naturally (acknowledge → practice
     → follow-up → small-talk → new question)
  5. Optionally uses Gemini LLM (if GEMINI_API_KEY configured) for richer replies
"""
import re
import json
import random
from pathlib import Path
from typing import Optional, Dict, Any, List

BASE_DIR = Path(__file__).resolve().parent
CONVERSATIONS_FILE = BASE_DIR / "mzungu_conversations.json"

# ── Load 1,000 conversations ─────────────────────────────────────────────────
ALL_CONVERSATIONS: List[Dict[str, Any]] = []
if CONVERSATIONS_FILE.exists():
    with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
        ALL_CONVERSATIONS = json.load(f)

# ── Per-user rotation tracking ────────────────────────────────────────────────
USER_ROTATION_INDEX: Dict[int, int] = {}
GLOBAL_ROTATION_INDEX = 0

# ── Vocabulary reference (English → Swahili primary, alt, example sentence) ──
VOCAB_MAP = {
    "fear": ("hofu", "woga", "Nina hofu ya giza"),
    "soldier": ("mwanajeshi", "askari", "Askari yuko doria"),
    "trousers": ("suruali", "suruali yangu", "Nilinunua suruali mpya"),
    "electricity": ("umeme", "stima", "Umeme umekatika"),
    "fish": ("samaki", "dagaa", "Napenda kula samaki"),
    "egg": ("yai", "mayai", "Nimenunua mayai matatu"),
    "cooking oil": ("mafuta ya kupikia", "mafuta", "Weka mafuta kidogo"),
    "church": ("kanisa", "kanisani", "Jumapili nitaenda kanisani"),
    "head": ("kichwa", "kichwa kinauma", "Kichwa changu kimepona"),
    "road": ("barabara", "njia", "Barabara hii inaenda wapi?"),
    "father": ("baba", "mzazi", "Baba yangu yuko nyumbani"),
    "elephant": ("tembo", "ndovu", "Niliona tembo kule Serengeti"),
    "pillow": ("mto", "mto wa kulalia", "Naomba mto laini"),
    "hair": ("nywele", "nywele ndefu", "Amenyoa nywele zake"),
    "water": ("maji", "maji ya kunywa", "Naomba maji ya baridi"),
    "driver": ("dereva", "nahodha", "Dereva wa basi yupo wapi?"),
    "phone": ("simu", "simu ya mkononi", "Namba yangu ya simu ni hii"),
    "window": ("dirisha", "madirisha", "Fungua dirisha tafadhali"),
    "bank": ("benki", "benki ya NMB au CRDB", "Nahitaji kwenda benki"),
    "dog": ("mbwa", "mbwa mkali", "Mbwa anabweka"),
    "meat": ("nyama", "nyama ya ng'ombe au kuku", "Tupike nyama leo"),
    "coffee": ("kahawa", "kahawa ya moto", "Asubuhi nakunywa kahawa"),
    "heart": ("moyo", "moyo wangu", "Ananifurahisha sana moyoni"),
    "soap": ("sabuni", "sabuni ya kuogea", "Naomba sabuni ya kunawia"),
    "teacher": ("mwalimu", "mkufunzi", "Mwalimu wangu ananifundisha vizuri"),
    "mosque": ("msikiti", "msikitini", "Ijumaa nitaenda msikitini"),
    "hotel": ("hoteli", "mkahawa", "Hoteli hii ina vyakula vizuri"),
    "pineapple": ("nanasi", "mananasi", "Nanasi hili ni tamu sana"),
    "bread": ("mkate", "mikate", "Chai na mkate asubuhi"),
    "farmer": ("mkulima", "mkulima wa mpunga", "Mkulima anavuna mazao"),
    "month": ("mwezi", "miezi", "Mwezi huu nimejifunza mengi"),
    "watch": ("saa", "saa ya mkononi", "Saa yangu inatembea sawa"),
    "clock": ("saa", "saa ya ukutani", "Saa inaonyesha saa tano"),
    "child": ("mtoto", "watoto", "Mtoto anacheza mpira"),
    "mountain": ("mlima", "Mlima Kilimanjaro", "Mlima mrefu zaidi barani Afrika"),
    "hand": ("mkono", "mikono", "Nawa mikono kwa maji tiririka"),
    "school": ("shule", "shuleni", "Watoto wako shuleni"),
    "friend": ("rafiki", "marafiki", "Wewe ni rafiki yangu mzuri"),
    "car": ("gari", "motokaa", "Gari hili ni zuri sana"),
    "hospital": ("hospitali", "zahanati", "Daktari yupo hospitalini"),
    "chair": ("kiti", "viti", "Kaa kwenye kiti hiki"),
    "food": ("chakula", "vyakula", "Chakula cha Kitanzania kina ladha nzuri"),
    "year": ("mwaka", "miaka", "Mwaka huu nitaitembelea Tanzania"),
    "police officer": ("polisi", "askari polisi", "Kituo cha polisi kipo karibu"),
    "table": ("meza", "meza ya chakula", "Weka sahani mezani"),
    "market": ("soko", "sokoni", "Nitaenda sokoni kununua mboga"),
    "chicken": ("kuku", "nyama ya kuku", "Kuku wa kienyeji ni mtamu"),
    "shoes": ("viatu", "viatu vya miguu", "Viatu vyangu vimekauka"),
    "engineer": ("mhandisi", "injinia", "Mhandisi anajenga jengo"),
    "potato": ("kiazi", "viazi", "Napenda chipsi za viazi"),
    "key": ("ufunguo", "funguo", "Ufunguo wa mlango wangu"),
    "mango": ("embe", "maembe", "Embe hili limeiva vizuri"),
    "mother": ("mama", "mzazi", "Mama yangu ananipigia simu"),
    "cloud": ("wingu", "mawingu", "Mawingu mazito angani"),
    "wind": ("upepo", "upepo mwanana", "Upepo unavuma vizuri"),
    "cat": ("paka", "paka mdogo", "Paka analala chini ya meza"),
    "salt": ("chumvi", "chumvi kidogo", "Chakula hiki hakina chumvi"),
    "clothes": ("nguo", "nguo safi", "Nahitaji kufulia nguo zangu"),
    "rain": ("mvua", "mvua kubwa", "Mvua inanyesha sana leo"),
    "toilet": ("choo", "msala", "Choo kipo wapi tafadhali?"),
    "hat": ("kofia", "kofia ya jua", "Kofia yangu inanikinga na jua"),
    "shop": ("duka", "dukani", "Naenda dukani kununua sukari"),
    "soup": ("supu", "supu ya kuku au ng'ombe", "Supu ya asubuhi inanipa nguvu"),
    "cow": ("ng'ombe", "ng'ombe wa maziwa", "Ng'ombe wanakula majani"),
    "book": ("kitabu", "vitabu", "Ninasoma kitabu cha Kiswahili"),
    "bird": ("ndege", "ndege wa angani", "Ndege anaimba mtini"),
    "door": ("mlango", "milango", "Funga mlango kwa usalama"),
    "airport": ("uwanja wa ndege", "kiwanja cha ndege", "Ndege inatua uwanjani"),
    "tomato": ("nyanya", "nyanya mbichi", "Weka nyanya kwenye mchuzi"),
    "bus": ("basi", "daladala", "Basi litaondoka saa ngapi?"),
    "money": ("pesa", "fedha", "Sina pesa taslimu sasa hivi"),
    "forest": ("msitu", "misitu", "Wanyama wanaishi msituni"),
    "bag": ("begi", "mkoba", "Begi langu lina vitabu"),
    "office": ("ofisi", "ofisini", "Mkurugenzi yupo ofisini"),
    "blanket": ("blanketi", "mablanketi", "Nafunikwa na blanketi la joto"),
    "shirt": ("shati", "mashati", "Shati langu jeupe"),
    "doctor": ("daktari", "mganga", "Daktari anapima wagonjwa"),
    "sugar": ("sukari", "sukari ya chai", "Chai bila sukari"),
    "minute": ("dakika", "dakika tano", "Nisubiri kwa dakika chache"),
    "week": ("wiki", "wiki ijayo", "Wiki hii nimejifunza maneno mengi"),
    "banana": ("ndizi", "ndizi mbivu", "Ndizi za Bukoba ni tamu"),
    "rice": ("mchele", "wali", "Nitanunua mchele kupika wali"),
    "sun": ("jua", "mwanga wa jua", "Jua linawaka kali sana"),
    "eye": ("jicho", "macho", "Macho yangu yanaona mbali"),
    "tea": ("chai", "chai ya rangi", "Tunywe chai ya maziwa"),
    "lion": ("simba", "mfalme wa nyika", "Simba ananguruma mbugani"),
    "stomach": ("tumbo", "tumbo linauma", "Kunywa maji mengi kwa afya ya tumbo"),
    "river": ("mto", "mito", "Mto Rufiji ni mkubwa"),
    "leg": ("mguu", "miguu", "Mguu wangu unauma kidogo"),
    "cook": ("pika", "mpishi", "Ninapenda kupika chakula"),
    "towel": ("taulo", "kitambaa cha mwili", "Ninahitaji taulo baada ya kuoga"),
    "goat": ("mbuzi", "mbuzi wa nyama", "Mbuzi anakula majani"),
    "station": ("stesheni", "kituo cha treni", "Stesheni iko umbali gani?"),
    "beach": ("ufukwe", "pwani", "Napenda kutembea ufukweni"),
    "farm": ("shamba", "bustani", "Shamba letu lina mazao mengi"),
    "stadium": ("uwanja", "uwanja wa michezo", "Timu zinacheza uwanjani"),
}

# ── Verb reference map ────────────────────────────────────────────────────────
VERB_MAP = {
    "write": ("kuandika", "Ninataka kuandika barua"),
    "cook": ("kupika", "Ninataka kupika pilau"),
    "buy": ("kununua", "Ninataka kununua zawadi"),
    "open": ("kufungua", "Ninataka kufungua mlango"),
    "close": ("kufunga", "Ninataka kufunga duka"),
    "travel": ("kusafiri", "Ninataka kusafiri kwenda Arusha"),
    "know": ("kujua", "Ninataka kujua Kiswahili vizuri"),
    "work": ("kufanya kazi", "Ninataka kufanya kazi Tanzania"),
    "understand": ("kuelewa", "Ninataka kuelewa zaidi"),
    "sing": ("kuimba", "Ninataka kuimba kwaya"),
    "help": ("kusaidia", "Ninataka kusaidia jamii"),
    "run": ("kukimbia", "Ninataka kukimbia asubuhi"),
    "wash": ("kuosha", "Ninataka kuosha vyombo"),
    "see": ("kuona", "Ninataka kuona wanyama Serengeti"),
    "drink": ("kunywa", "Ninataka kunywa maji"),
    "sleep": ("kulala", "Ninataka kulala mapema"),
    "love": ("kupenda", "Ninataka kupenda utamaduni wenu"),
    "like": ("kupenda", "Ninapenda Kiswahili sana"),
    "arrive": ("kufika", "Ninataka kufika salama"),
    "laugh": ("kucheka", "Ninataka kucheka na marafiki"),
    "eat": ("kula", "Ninataka kula ugali na samaki"),
    "play": ("kucheza", "Ninataka kucheza mpira"),
    "remember": ("kukumbuka", "Ninataka kukumbuka maneno haya"),
    "wait": ("kusubiri", "Ninataka kusubiri basi"),
    "speak": ("kuongea", "Ninataka kuongea Kiswahili fasaha"),
    "sell": ("kuuza", "Ninataka kuuza bidhaa"),
    "clean": ("kusafisha", "Ninataka kusafisha chumba changu"),
    "read": ("kusoma", "Ninataka kusoma vitabu"),
    "study": ("kusoma", "Ninataka kusoma vizuri"),
    "pay": ("kulipa", "Ninataka kulipa kwa M-Pesa"),
    "walk": ("kutembea", "Ninataka kutembea ufukweni"),
    "think": ("kufikiri", "Ninataka kufikiri kwa kina"),
    "stay": ("kukaa", "Ninataka kukaa Tanzania miaka mitatu"),
    "go": ("kwenda", "Ninataka kwenda Zanzibar"),
    "come": ("kuja", "Ninataka kuja tena Tanzania"),
    "teach": ("kufundisha", "Ninataka kufundisha watoto"),
    "learn": ("kujifunza", "Ninataka kujifunza Kiswahili"),
    "ask": ("kuuliza", "Ninataka kuuliza swali"),
    "answer": ("kujibu", "Ninataka kujibu vizuri"),
    "sit": ("kukaa", "Ninataka kukaa hapa"),
    "stand": ("kusimama", "Ninataka kusimama kidogo"),
    "give": ("kutoa", "Ninataka kutoa zawadi"),
    "take": ("kuchukua", "Ninataka kuchukua picha"),
    "bring": ("kuleta", "Ninataka kuleta chakula"),
    "start": ("kuanza", "Ninataka kuanza mazungumzo"),
    "finish": ("kumaliza", "Ninataka kumaliza kazi yangu"),
    "look": ("kutazama", "Ninataka kutazama mbali"),
    "hear": ("kusikia", "Ninataka kusikia muziki"),
    "tell": ("kusema", "Ninataka kusema ukweli"),
    "meet": ("kukutana", "Ninataka kukutana na wenzangu"),
    "visit": ("kutembelea", "Ninataka kutembelea Serengeti"),
    "swim": ("kuogelea", "Ninataka kuogelea baharini"),
    "drive": ("kuendesha", "Ninataka kuendesha gari"),
    "call": ("kupiga simu", "Ninataka kupiga simu"),
    "send": ("kutuma", "Ninataka kutuma ujumbe"),
    "receive": ("kupokea", "Ninataka kupokea malipo"),
    "show": ("kuonyesha", "Ninataka kuonyesha njia"),
    "use": ("kutumia", "Ninataka kutumia M-Pesa"),
    "jump": ("kuruka", "Ninataka kuruka juu"),
    "dance": ("kucheza dansi", "Ninataka kucheza dansi ya ngoma"),
    "sing": ("kuimba", "Ninataka kuimba wimbo wa Tanzania"),
    "pray": ("kusali", "Ninataka kusali msikitini"),
    "rest": ("kupumzika", "Ninataka kupumzika baada ya safari"),
    "go back": ("kurudi", "Ninataka kurudi nyumbani"),
    "return": ("kurudi", "Ninataka kurudi Tanzania tena"),
    "enter": ("kuingia", "Ninataka kuingia nyumbani"),
    "leave": ("kutoka", "Ninataka kutoka sasa hivi"),
    "forget": ("kusahau", "Sitaki kusahau ukarimu wenu"),
}

# ── Natural multi-turn conversation templates per category ────────────────────
# Each category has: ack (acknowledge teacher's reply) + followup (follow-up questions)
CATEGORY_FLOWS = {
    "Learning/Classroom": {
        "ack": [
            "Ahsante sana mwalimu! Sasa nimeelewa vizuri. Nitaandika hilo kwenye daftari langu mara moja.",
            "Wow, hiyo ni rahisi zaidi kuliko nilivyofikiri! Nashukuru sana kwa maelezo yako mwalimu.",
            "Sasa nimeona! Nilikuwa nikichanganya lakini maelezo yako yamefungua akili yangu. Asante mwalimu!",
            "Nimeelewa vizuri mwalimu! Una njia ya kipekee sana ya kueleza mambo magumu kwa urahisi.",
        ],
        "followup": [
            "Je, kuna maneno mengine yanayofanana na hilo ambazo ninapaswa kujifunza?",
            "Niambie, katika mazungumzo ya kila siku, sentensi hiyo inatumika mara ngapi?",
            "Ningependa kujaribu kutumia neno hilo katika sentensi. Je, hii inasikika vizuri: ?",
            "Mwalimu, nikiwa Tanzania na kutumia neno hilo, watu wataelewa bila shida?",
        ],
    },
    "Actions/Verbs": {
        "ack": [
            "Ahaa! Kumbe sahihi ni hivyo. Asante kwa kunisahihisha mwalimu — sasa nimekariri!",
            "Nimeelewa! Kitenzi hicho kinatumika tofauti na nilivyodhani. Nashukuru sana kwa mwanga huo.",
            "Safi sana! Nilichanganya Kiingereza na Kiswahili — sasa ninajua jinsi sahihi ya kusema.",
            "Asante kwa marekebisho mwalimu! Wakati mwingine lugha mbili zinachanganyikana kichwani mwangu.",
        ],
        "followup": [
            "Je, kitenzi hiki kinabadilika jinsi gani kwa wakati uliopita na wakati ujao?",
            "Nikiandika 'watatembea' maana yake watu wengi watatembea, sivyo? Nimesema sawa?",
            "Mwalimu, napenda kujua — kitenzi hicho kina mnyambuliko gani wa kawaida?",
            "Ukinionyesha mfano wa sentensi nyingine inayotumia kitenzi hiki, itanisaidia zaidi!",
        ],
    },
    "Shopping": {
        "ack": [
            "Asante sana mwalimu! Sasa nitajua jinsi ya kujadiliana bei nikiwa sokoni bila aibu.",
            "Hii ni muhimu sana kujua! Mara nyingi wauzaji wanaona mzungu wananiuzia ghali zaidi.",
            "Nimeelewa vizuri! Maneno sahihi yanadhibiti bei ya bidhaa. Nitayatumia soko lijalo!",
            "Safi kabisa mwalimu! Tanzania ina utamaduni mzuri wa kujadiliana bei — napenda hilo.",
        ],
        "followup": [
            "Je, nikisema 'bei ni ghali sana' wauzaji wanakasirika au wanaelewa tu?",
            "Mwalimu, maneno gani ninaweza kutumia kuomba punguzo zaidi bila kukera?",
            "Niambie, sokoni kawaida mtu anapata punguzo la asilimia ngapi akijadiliana vizuri?",
            "Je, kuna tofauti kati ya kujadiliana bei dukani na kujadiliana sokoni?",
        ],
    },
    "Locations": {
        "ack": [
            "Asante sana kwa maelekezo mwalimu! Sasa nitaweza kufika mahali ninapotaka bila kupotea.",
            "Vizuri sana! Maneno hayo ni rahisi kukumbuka. Nitayatumia ninapouliza watu barabarani.",
            "Nimeelewa mwalimu! Tanzania ina mfumo mzuri wa maelekezo — naipenda hilo.",
            "Nashukuru sana! Nilikuwa na wasiwasi wa kupoteza njia, lakini sasa ninajiamini zaidi.",
        ],
        "followup": [
            "Mwalimu, kwa kawaida ninaweza kupanda daladala au ni bora kutumia bodaboda?",
            "Je, kuna maneno mengine ya mwelekeo ninayopaswa kujifunza — kama kulia, kushoto?",
            "Niambie, Tanzania watu wanafurahia kusaidia wageni kupata njia?",
            "Ikiwa sijui njia na ninaomba msaada, ninasema nini hasa ili niwe na adabu?",
        ],
    },
    "Wants/Needs": {
        "ack": [
            "Ahaa! Kwa hiyo badala ya kusema neno la Kiingereza, nitumie neno sahihi la Kiswahili. Asante mwalimu!",
            "Nimeelewa vizuri! Sasa nitasema kwa Kiswahili fasaha zaidi ninapoomba kitu.",
            "Safi sana mwalimu! Hii itanisaidia sana kuwasiliana vizuri na wenyeji wa Tanzania.",
            "Nashukuru! Nilikuwa nikichanganya maneno ya Kiingereza lakini sasa najua jinsi sahihi ya kuomba.",
        ],
        "followup": [
            "Mwalimu, kwa adabu zaidi ninaongeza nini baada ya kuomba — 'tafadhali' au 'asante'?",
            "Je, kuna tofauti kati ya 'naomba' na 'nataka' ukiomba kitu dukani?",
            "Niambie, Watanzania wanaona ni adabu zaidi kusema vipi ninapoomba msaada?",
            "Ukinionyesha jinsi ya kuomba hiyo kitu kwa heshima kubwa zaidi, itakuwa vizuri sana!",
        ],
    },
    "Greetings mix": {
        "ack": [
            "Asante sana mwalimu! Sasa naelewa jinsi ya kutoa salamu vizuri. Watanzania watafurahi kusikia!",
            "Nimeelewa! Salamu za Kiswahili zina uzuri na kina tofauti na matarajio yangu.",
            "Safi sana! Nitafanya mazoezi ya salamu hizi hadi niziseme bila shida yoyote.",
            "Nashukuru sana! Nikiamkua watu vizuri, itaonyesha ninaheshimu utamaduni wao.",
        ],
        "followup": [
            "Je, salamu hiyo inatumika asubuhi peke yake au wakati wote wa siku?",
            "Mwalimu, watu wa zamani wanaitwa vipi tofauti na watu wa vijana Tanzania?",
            "Niambie, kuna salamu za kipekee za mikoa mbalimbali Tanzania?",
            "Nikiamkua mtu mkubwa umri kwa Kiswahili, ninasema nini hasa?",
        ],
    },
    "Transport": {
        "ack": [
            "Asante mwalimu! Sasa nitajua jinsi ya kupanda usafiri wa umma Tanzania bila msongo.",
            "Hii ni muhimu sana! Nilikuwa na wasiwasi kuhusu usafiri — sasa ninajiamini zaidi.",
            "Nimeelewa vizuri! Tanzania ina mifumo mingi ya usafiri — ni ya kuvutia kujifunza.",
            "Nashukuru sana kwa maelezo hayo. Nitayatumia safari yangu ijayo Tanzania!",
        ],
        "followup": [
            "Mwalimu, nauli ya daladala inaweza kubadilika au ina bei maalum?",
            "Je, ni salama zaidi kupanda boda boda au daladala usiku Tanzania?",
            "Nikiwa sijui bei ya nauli, ninaweza kusemaje kuomba watu wanieleze?",
            "Mwalimu, mabasi ya muda mrefu kama Dar es Salaam kwenda Arusha — yanaitwa nini?",
        ],
    },
    "Small talk": {
        "ack": [
            "Asante sana mwalimu! Hilo linafanya mazungumzo yetu yawe ya kibinadamu zaidi.",
            "Nimeelewa vizuri! Kuzungumza kuhusu maisha ya kila siku ni njia nzuri ya kuboresha Kiswahili.",
            "Nashukuru sana! Ninafurahi sana kujua zaidi kuhusu maisha ya Tanzania.",
            "Safi sana! Una hadithi nyingi za kuvutia. Ninapenda kujua zaidi!",
        ],
        "followup": [
            "Mwalimu, Tanzania kwa kawaida watu wanafanya nini wakati wa mapumziko yao?",
            "Je, chakula kinachopendwa zaidi Tanzania nyakati za sherehe ni kipi?",
            "Niambie kidogo kuhusu muziki unaopendwa Tanzania siku hizi!",
            "Je, michezo inayopendwa na vijana wa Tanzania ni ipi hasa?",
        ],
    },
    "Culture": {
        "ack": [
            "Wow! Hilo ni la kuvutia sana! Utamaduni wa Tanzania una kina kubwa kuliko nilivyodhani.",
            "Nashukuru sana kwa maelezo hayo ya kina mwalimu! Kujua utamaduni kunaboresha uelewa wa lugha.",
            "Nimeelewa vizuri! Hakika utamaduni na lugha vinahusiana sana — haviwezi kutengwa.",
            "Asante sana! Hilo linaonyesha kwamba Kiswahili ni zaidi ya maneno — ni njia ya maisha.",
        ],
        "followup": [
            "Mwalimu, kuna mila au desturi nyingine za kipekee Tanzania ambazo mgeni anapaswa kujua?",
            "Je, kuna mambo ambayo mgeni anapaswa kuepuka kufanya Tanzania ili asiudhi wenyeji?",
            "Niambie zaidi kuhusu sherehe maarufu za Tanzania ambazo ningependa kushiriki!",
            "Utamaduni wa Zanzibar unatofautiana vipi na utamaduni wa Tanzania bara?",
        ],
    },
    "Numbers/Time": {
        "ack": [
            "Ahaa! Sasa nimeelewa mfumo wa saa za Kiswahili. Unatofautiana kabisa na Kiingereza!",
            "Nashukuru sana! Namba za Kiswahili zina mpangilio wa kipekee — lazima nifanye mazoezi zaidi.",
            "Nimeelewa! Mfumo wa saa wa Tanzania una mantiki yake — sasa naanza kuona jinsi inavyofanya kazi.",
            "Safi sana mwalimu! Saa sita mchana maana yake saa 12 noon — sivyo? Nimesema sawa?",
        ],
        "followup": [
            "Mwalimu, jinsi ya kusema tarehe kwa Kiswahili — ninaanza na nini, mwezi au tarehe?",
            "Je, wiki zinaanzaje Tanzania — Jumatatu au Jumapili?",
            "Nikiuliza mtu 'kipindi' cha mikutano, nikimaanisha 'schedule', ninasema nini?",
            "Mwalimu, maneno ya wakati kama 'jana', 'leo', 'kesho' — ni rahisi kukumbuka, sivyo?",
        ],
    },
    "Health": {
        "ack": [
            "Asante sana mwalimu! Maneno haya ya afya ni muhimu sana kuwa nayo nikiwa Tanzania.",
            "Nimeelewa vizuri! Nikiwa mgonjwa, sasa najua jinsi ya kueleza dalili zangu kwa daktari.",
            "Nashukuru! Afya ni muhimu kuliko yote — vizuri kujua jinsi ya kuomba msaada wa haraka.",
            "Safi sana mwalimu! Hii inanipa uhakika zaidi nikitembea Tanzania bila woga.",
        ],
        "followup": [
            "Mwalimu, zahanati na hospitali Tanzania zinapatikana kila mahali au zinatofautiana kwa mkoa?",
            "Je, dawa za kawaida zinauzwa dukani au lazima niwe na daktari?",
            "Nikiwa na tatizo la afya na sijui Kiswahili vizuri, nifanye nini hospitali?",
            "Niambie, matibabu ya asili — dawa za mitishamba — yanatumika Tanzania?",
        ],
    },
    "Politeness": {
        "ack": [
            "Asante sana mwalimu! Adabu na heshima ni nguzo ya utamaduni wa Tanzania — napenda hilo sana.",
            "Nimeelewa vizuri! Maneno ya adabu yanafungua milango mingi — ni kweli kabisa.",
            "Safi sana! Nikiwa na adabu, wenyeji watanisaidia zaidi na mazungumzo yatakuwa mazuri.",
            "Nashukuru sana mwalimu! Heshima ni lugha ya ulimwengu wote, lakini kila tamaduni ina njia yake.",
        ],
        "followup": [
            "Mwalimu, kuna maneno ya adabu ya karibu zaidi — kwa familia au marafiki wa karibu?",
            "Je, Watanzania wanaona aibu kubwa mtu asiyesema 'asante' baada ya kupata msaada?",
            "Niambie, kuna njia nyingine za kuomba msamaha kwa makosa makubwa?",
            "Ukinionyesha jinsi ya kuomba msamaha kwa heshima zaidi, itanisaidia sana!",
        ],
    },
    "Farewell": {
        "ack": [
            "Asante sana mwalimu! Sasa najua jinsi ya kuaga vizuri — hata hilo linaonyesha heshima.",
            "Nimeelewa! Uagano mzuri ni muhimu kama salamu nzuri — ni mzunguko kamili wa mazungumzo.",
            "Nashukuru sana! Nitafurahia kutumia maneno hayo ya kuaga mara ninapokwisha darasa.",
            "Safi sana mwalimu! Kiswahili kina maneno mazuri sana ya kuonesha hisia za kweli.",
        ],
        "followup": [
            "Mwalimu, 'tutaonana' inamaanisha 'tutaonana tena', sivyo? Maana yake ni ya matumaini.",
            "Je, kuna njia nyingine za kuaga rafiki wa karibu tofauti na mgeni tu?",
            "Niambie, baada ya darasa nzuri kama hii, ninasemaje kwa hisia za kweli?",
            "Mwalimu, nimefurahia sana kipindi hiki. Ninaweza kuja tena kipindi kingine?",
        ],
    },
}

# ── Intro greeting templates ───────────────────────────────────────────────────
INTRO_GREETINGS = [
    "Habari yako mwalimu! Natumai unaendelea salama huko Tanzania.",
    "Jambo mwalimu! Nimefurahi sana kuunganishwa na wewe leo.",
    "Shikamoo mwalimu! Natumai siku yako inaenda vizuri sana.",
    "Habari za asubuhi mwalimu! Nipo tayari kwa kipindi chetu cha Kiswahili.",
    "Habari za mchana mwalimu! Nimekuwa nikisubiri kwa hamu darasa letu la leo.",
    "Good day mwalimu! Naitwa {name}. Nimefurahi sana kupata nafasi ya kujifunza na wewe.",
    "Jambo sana mwalimu! Naitwa {name}. Leo nina hamu kubwa ya kufanya mazoezi ya kuongea.",
    "Hello mwalimu! Natumai uko poa kabisa. Mimi ni {name} na leo nataka nifanye mazoezi ya Kiswahili.",
    "Habari mwalimu! Naitwa {name}. Asante sana kwa kuwa mwalimu wangu leo.",
    "Hi mwalimu! Nimefurahi kukutana na wewe kwenye ChatPay.",
    "Habari za leo mwalimu! Naitwa {name}. Nimejiandaa vizuri sana na maswali yangu ya Kiswahili.",
    "Hujambo mwalimu! Naitwa {name} na ninatoka {country}. Nimefurahi sana kujifunza nawe!",
]

COUNTRIES = ["Sweden", "Ujerumani", "Ufaransa", "Uingereza", "Marekani", "Norway", "Denmark", "Holland"]

TRANSITION_PHRASES = [
    "Kuna jambo moja nimekuwa nikijiuliza tangu asubuhi —",
    "Nilikuwa nikijaribu kutunga sentensi hii kwenye daftari langu lakini sina uhakika kama niko sahihi —",
    "Mwalimu, nimeandika sentensi hii kwenye kitabu changu lakini sijui kama ni sahihi —",
    "Naomba unisaidie kuelewa hili vizuri —",
    "Ningependa kufanya mazoezi ya sentensi hii —",
    "Nilikuwa nikifanya mazoezi nikakwama kidogo hapa —",
    "Kuna kitu nilitaka unieleweshe kwa Kiswahili fasaha —",
    "Kama mgeni ninayejifunza Kiswahili, hili swali limekuwa likinichanganya —",
    "Naomba unisahihishe kama hapa nimesema sawa —",
    "Nina swali la haraka kuhusu matumizi ya maneno —",
    "Mwalimu, leo nilitaka kufanya mazoezi hasa kuhusu hili —",
    "Nilisikia sentensi hii wikendi iliyopita nikawa na shaka —",
]


# ── Public API ────────────────────────────────────────────────────────────────

def get_next_rotational_prompt(user_id: Optional[int] = None) -> Dict[str, Any]:
    """Returns the next prompt in round-robin rotation (1 → 2 → … → 1000 → 1)."""
    global GLOBAL_ROTATION_INDEX
    if not ALL_CONVERSATIONS:
        return {"id": 1, "category": "General",
                "mzungu_message": "Habari yako mwalimu! Nipo tayari kuanza darasa letu la Kiswahili leo."}
    total = len(ALL_CONVERSATIONS)
    if user_id is not None:
        idx = USER_ROTATION_INDEX.get(user_id, 0)
        prompt = ALL_CONVERSATIONS[idx % total]
        USER_ROTATION_INDEX[user_id] = (idx + 1) % total
    else:
        prompt = ALL_CONVERSATIONS[GLOBAL_ROTATION_INDEX % total]
        GLOBAL_ROTATION_INDEX = (GLOBAL_ROTATION_INDEX + 1) % total
    return prompt


def get_prompt_by_id(prompt_id: int) -> Optional[Dict[str, Any]]:
    """Fetch prompt by exact ID (1-1000)."""
    for p in ALL_CONVERSATIONS:
        if p["id"] == prompt_id:
            return p
    return None


def generate_intro_message(partner_name: str, prompt: Dict[str, Any]) -> str:
    """
    Builds a unique, natural-sounding opening message every time so teachers
    never get the same greeting twice. Combines greeting + transition + prompt question.
    """
    country = random.choice(COUNTRIES)
    greeting = random.choice(INTRO_GREETINGS).replace("{name}", partner_name).replace("{country}", country)
    transition = random.choice(TRANSITION_PHRASES)
    mzungu_question = prompt.get("mzungu_message", "").strip()

    style = random.randint(1, 5)
    if style == 1:
        return f"{greeting} {transition} {mzungu_question}"
    elif style == 2:
        return f"{greeting} Leo nilikuwa nikijiuliza: {mzungu_question}"
    elif style == 3:
        return f"{greeting} {mzungu_question}"
    elif style == 4:
        return f"{greeting} Kuna kitu nilitaka unieleweshe mwalimu — {mzungu_question}"
    else:
        return f"{greeting} Naomba unisaidie kuelewa hili vizuri: {mzungu_question}"


def generate_intelligent_reply(
    partner_name: str,
    teacher_message: str,
    current_prompt: Optional[Dict[str, Any]] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Multi-turn, contextual reply engine.

    Turn 0 (teacher sends first reply after opening prompt):
      → Mzungu acknowledges specifically what the teacher corrected/explained,
        repeats/practices the corrected form, and shows natural gratitude.

    Turn 1+ (subsequent messages):
      → Mzungu asks a natural follow-up question related to the same topic/category,
        or reacts to any new content the teacher provides.

    The reply always relates directly to the conversation topic — never generic filler.
    """
    t_msg = teacher_message.strip()
    t_lower = t_msg.lower()
    partner_first = partner_name.split()[0] if partner_name else "Rafiki"

    prompt_msg = (current_prompt.get("mzungu_message", "") if current_prompt else "").strip()
    prompt_lower = prompt_msg.lower()
    category = (current_prompt.get("category", "Learning/Classroom") if current_prompt else "Learning/Classroom").strip()

    # ── Determine turn number and message count from history ─────────────────
    history = conversation_history or []
    # Count how many mzungu (bot) messages have been sent already
    bot_turn = sum(1 for m in history if m.get("role") == "bot")
    teacher_msgs_count = sum(1 for m in history if m.get("role") == "teacher")

    # ── 11TH MESSAGE (Final Closing Wrap-Up) ──────────────────────────────────
    # If the room has 9 or 10 messages (or teacher has sent 5 replies),
    # this bot response is the 11th message that cleanly concludes the session.
    if len(history) >= 9 or teacher_msgs_count >= 5:
        closing_replies = [
            f"Asante sana mwalimu kwa darasa hili zuri na lenye mafunzo tele! Nimefurahi sana na nimejifunza mambo mengi mno leo. Malipo yako yameidhinishwa kikamilifu kwenye pochi yako ya ChatPay. Mazungumzo yetu ya leo yamekamilika, tutaonana tena kesho!",
            f"Nashukuru sana mwalimu! Mazungumzo yetu ya leo yamekuwa ya faida kubwa sana kwangu na yamenijengea kujiamini. Mfumo unakamilisha malipo yako papo hapo kwenye pochi yako. Nitarudi tena kesho tufanye mazoezi zaidi!",
            f"Hongera sana na asante mwalimu kwa uvumilivu na ufafanuzi wako mzuri! Hakika leo nimepiga hatua kubwa. Malipo yako yametumwa moja kwa moja kwenye pochi yako ya ChatPay. Tuonane tena kesho!",
            f"Aha! Nimefurahia kila dakika ya kipindi hiki mwalimu. Umekuwa mwalimu bora sana leo! Malipo yako yamekamilika sasa hivi. Tutaendelea tena kesho!",
        ]
        return random.choice(closing_replies)

    # ── Handle very short social responses ("asante", "nzuri", "ok", "sawa") ─
    short_social = {"asante", "ok", "sawa", "nzuri", "poa", "vizuri", "sawa sawa", "ndiyo",
                    "sure", "good", "fine", "great", "yes", "okay", "alright", "perfect"}
    words_in_reply = set(t_lower.split())
    if len(t_lower.split()) <= 3 and (words_in_reply & short_social):
        # The teacher gave a short acknowledgement — mzungu continues with a follow-up
        flows = CATEGORY_FLOWS.get(category, CATEGORY_FLOWS["Learning/Classroom"])
        followup = random.choice(flows["followup"])
        openers = [
            f"Nashukuru sana! {followup}",
            f"Safi kabisa! {followup}",
            f"Nzuri sana mwalimu! {followup}",
            f"Asante kwa uvumilivu wako. {followup}",
        ]
        return random.choice(openers)

    # ── VOCABULARY: "How do you say '<word>' kwa Kiswahili?" ─────────────────
    m = re.search(r"how do you say '([^']+)'", prompt_msg, re.IGNORECASE)
    if m:
        target_en = m.group(1).lower().strip()
        vocab_info = VOCAB_MAP.get(target_en)
        if vocab_info:
            sw_primary, sw_alt, sample_sentence = vocab_info
            # Detect which Swahili word the teacher mentioned
            detected = sw_primary
            if sw_alt and sw_alt in t_lower:
                detected = sw_alt
            elif sw_primary in t_lower:
                detected = sw_primary

            if bot_turn == 0:
                # First acknowledgement — specific to the word learned
                responses = [
                    f"Ahsante sana mwalimu! Kumbe neno sahihi ni \"{detected}\". "
                    f"Sasa naelewa! Je, ninaweza kusema \"{sample_sentence}\"?",
                    f"Aha, nimeelewa! \"{detected}\" — nimeiandika mara moja. "
                    f"Kwa hiyo sentensi kamili inaweza kuwa: \"{sample_sentence}\" — imekubalika mwalimu?",
                    f"Nashukuru sana! \"{detected}\" — matamshi yake yanasikika vipi? "
                    f"Kama nikiitamka polepole: {'-'.join(list(detected)[:4])}... ni sahihi?",
                    f"Nimefurahi sana kujifunza! Neno \"{detected}\" linatoka wapi asili yake — lina historia yoyote ya kuvutia?",
                ]
            else:
                # Follow-up turn — expand on the topic
                flows = CATEGORY_FLOWS.get(category, CATEGORY_FLOWS["Learning/Classroom"])
                followup = random.choice(flows["followup"])
                responses = [
                    f"Asante kwa maelezo yako ya kina! {followup}",
                    f"Nimejifunza neno jipya leo — \"{detected}\". {followup}",
                    f"Una subira kubwa mwalimu! {followup}",
                ]
            return random.choice(responses)

    # ── VERBS: "How do I say 'I want to <verb>'?" ─────────────────────────────
    m_verb = re.search(r"how do i say 'i want to ([^']+)'", prompt_msg, re.IGNORECASE)
    if m_verb:
        target_verb = m_verb.group(1).lower().strip()
        verb_info = VERB_MAP.get(target_verb)
        if verb_info:
            sw_verb, sample_s = verb_info
            if bot_turn == 0:
                responses = [
                    f"Ahaa! Kwa hiyo ninasema \"{sample_s}\" — kumbe rahisi hivyo! "
                    f"Nilikuwa nikichanganya jinsi ya kuunganisha 'ninataka' na kitenzi. Asante sana mwalimu!",
                    f"Safi sana! \"{sw_verb}\" — nimekariri. "
                    f"Je, kwa wakati uliopita nasema 'nilitaka {sw_verb}'? Imesemwa vizuri?",
                    f"Nashukuru! Sasa naweza kusema \"{sample_s}\" bila wasiwasi. "
                    f"Kiswahili kina mpangilio mzuri wa maneno — nakipenda zaidi kila siku!",
                ]
            else:
                flows = CATEGORY_FLOWS.get(category, CATEGORY_FLOWS["Actions/Verbs"])
                followup = random.choice(flows["followup"])
                responses = [
                    f"Umesaidia sana! {followup}",
                    f"Vizuri sana mwalimu! {followup}",
                    f"Nashukuru kwa uvumilivu wako mwalimu! {followup}",
                ]
            return random.choice(responses)

    # ── MIXED LANGUAGE: "Nita-walk", "ninataka ku-eat", etc. ─────────────────
    m_mix = re.search(r"\bni(?:ta|li|nataka ku)-([a-zA-Z]+)\b", prompt_lower, re.IGNORECASE)
    if m_mix:
        eng_verb = m_mix.group(1).lower()
        verb_info = VERB_MAP.get(eng_verb)
        sw_verb = verb_info[0] if verb_info else "kitenzi sahihi cha Kiswahili"
        sample_s = verb_info[1] if verb_info else f"Ninataka {sw_verb}"
        if bot_turn == 0:
            responses = [
                f"Ahh, nimeelewa! Badala ya kuchanganya Kiingereza, ninasema: \"{sample_s}\". "
                f"Nilikuwa nikichanganya lugha mbili — asante kwa kunisahihisha mwalimu!",
                f"Sawa sawa! Kitenzi sahihi ni \"{sw_verb}\" — hivyo sentensi nzima inakuwa \"{sample_s}\". "
                f"Itachukua muda kukumbuka lakini nitafanya mazoezi!",
                f"Nashukuru sana kwa marekebisho! Wakati mwingine lugha mbili zinachanganyikana kichwani mwangu. "
                f"Sasa nitaandika \"{sample_s}\" mara kumi ili nisahau!",
            ]
        else:
            flows = CATEGORY_FLOWS.get(category, CATEGORY_FLOWS["Actions/Verbs"])
            followup = random.choice(flows["followup"])
            responses = [f"Asante mwalimu! {followup}"]
        return random.choice(responses)

    # ── SHOPPING: price/bargaining questions ─────────────────────────────────
    if any(w in prompt_lower for w in ["how much", "bei gani", "punguz", "ghali", "bei ya"]):
        flows = CATEGORY_FLOWS.get("Shopping", CATEGORY_FLOWS["Learning/Classroom"])
        if bot_turn == 0:
            ack = random.choice(flows["ack"])
            followup = random.choice(flows["followup"])
            responses = [
                f"{ack} {followup}",
                f"Asante sana mwalimu! Nitayatumia maneno hayo sokoni mara moja. {followup}",
                f"Vizuri kabisa! Kujua jinsi ya kujadiliana bei kutanisaidia sana Tanzania. {followup}",
            ]
        else:
            followup = random.choice(flows["followup"])
            responses = [f"Nimejifunza mengi leo! {followup}",
                         f"Nashukuru sana mwalimu. {followup}"]
        return random.choice(responses)

    # ── LOCATIONS/DIRECTIONS ─────────────────────────────────────────────────
    if any(w in prompt_lower for w in ["kwenda", "wapi", "how do i get", "njia", "elekeza", "maelekezo"]):
        flows = CATEGORY_FLOWS.get("Locations", CATEGORY_FLOWS["Learning/Classroom"])
        if bot_turn == 0:
            ack = random.choice(flows["ack"])
            followup = random.choice(flows["followup"])
            return f"{ack} {followup}"
        else:
            followup = random.choice(flows["followup"])
            return f"Asante mwalimu! {followup}"

    # ── GREETINGS & FAREWELLS ─────────────────────────────────────────────────
    if any(w in prompt_lower for w in ["shikamoo", "karibu", "kwaheri", "tutaonana", "habari", "salamu"]):
        cat_key = "Farewell" if any(w in prompt_lower for w in ["kwaheri", "tutaonana", "see you"]) else "Greetings mix"
        flows = CATEGORY_FLOWS.get(cat_key, CATEGORY_FLOWS["Learning/Classroom"])
        if bot_turn == 0:
            ack = random.choice(flows["ack"])
            followup = random.choice(flows["followup"])
            return f"{ack} {followup}"
        else:
            followup = random.choice(flows["followup"])
            return f"Una maelezo mazuri sana! {followup}"

    # ── CULTURE / POLITENESS ─────────────────────────────────────────────────
    if any(w in prompt_lower for w in ["utamaduni", "hakuna matata", "pole", "samahani", "heshima", "desturi"]):
        flows = CATEGORY_FLOWS.get("Culture", CATEGORY_FLOWS["Learning/Classroom"])
        if bot_turn == 0:
            ack = random.choice(flows["ack"])
            followup = random.choice(flows["followup"])
            return f"{ack} {followup}"
        else:
            followup = random.choice(flows["followup"])
            return f"Nashukuru kwa ufafanuzi huo wa kina! {followup}"

    # ── TRANSPORT ─────────────────────────────────────────────────────────────
    if any(w in prompt_lower for w in ["nauli", "basi", "daladala", "bodaboda", "teksi", "treni", "stesheni"]):
        flows = CATEGORY_FLOWS.get("Transport", CATEGORY_FLOWS["Learning/Classroom"])
        if bot_turn == 0:
            ack = random.choice(flows["ack"])
            followup = random.choice(flows["followup"])
            return f"{ack} {followup}"
        else:
            followup = random.choice(flows["followup"])
            return f"Vizuri sana mwalimu! {followup}"

    # ── NUMBERS / TIME ────────────────────────────────────────────────────────
    if any(w in prompt_lower for w in ["saa", "tarehe", "mwezi", "mwaka", "namba", "hesabu", "jumla"]):
        flows = CATEGORY_FLOWS.get("Numbers/Time", CATEGORY_FLOWS["Learning/Classroom"])
        if bot_turn == 0:
            ack = random.choice(flows["ack"])
            followup = random.choice(flows["followup"])
            return f"{ack} {followup}"
        else:
            followup = random.choice(flows["followup"])
            return f"Nimeelewa vizuri! {followup}"

    # ── HEALTH ────────────────────────────────────────────────────────────────
    if any(w in prompt_lower for w in ["daktari", "hospitali", "mgonjwa", "dawa", "ugonjwa", "afya"]):
        flows = CATEGORY_FLOWS.get("Health", CATEGORY_FLOWS["Learning/Classroom"])
        if bot_turn == 0:
            ack = random.choice(flows["ack"])
            followup = random.choice(flows["followup"])
            return f"{ack} {followup}"
        else:
            followup = random.choice(flows["followup"])
            return f"Nashukuru sana! {followup}"

    # ── FALLBACK: Category-based acknowledgement + follow-up ─────────────────
    flows = CATEGORY_FLOWS.get(category, CATEGORY_FLOWS["Learning/Classroom"])
    ack = random.choice(flows["ack"])
    followup = random.choice(flows["followup"])

    # Extract any Swahili words from the teacher's reply to reference them
    # (heuristic: words > 4 chars that aren't English)
    sw_candidates = [w for w in t_msg.split() if len(w) > 4 and not re.match(r'^[A-Z][a-z]*$', w)]
    if sw_candidates and bot_turn == 0:
        picked = random.choice(sw_candidates[:3])
        continuations = [
            f"Ahsante sana mwalimu! Nimesikia vizuri — neno \"{picked}\" limenisaidia. {followup}",
            f"Nimeelewa! \"{picked}\" — neno hilo litabaki kichwani mwangu. {followup}",
            f"Safi kabisa! \"{picked}\" — nimeweka daftarini. {followup}",
        ]
        return random.choice(continuations)

    if bot_turn == 0:
        return f"{ack} {followup}"
    else:
        deepens = [
            f"Maelezo yako yanazidi kunifanya nielewe zaidi! {followup}",
            f"Una uvumilivu mkubwa sana mwalimu! {followup}",
            f"Kila jibu lako linaongeza uelewa wangu! {followup}",
            f"Nashukuru sana kwa muda wako! {followup}",
        ]
        return random.choice(deepens)
