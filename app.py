import streamlit as st
import requests, time, io, zipfile
from concurrent.futures import ThreadPoolExecutor

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
RETRY_CODES = {408, 429, 500, 502, 503, 504}

# nama AI -> kata kunci untuk mencari model gratis yang cocok
SLOT = {
    "DeepSeek": "deepseek",
    "GLM": "glm",
    "Kimi": "kimi",
    "Qwen": "qwen",
    "Llama": "llama",
    "Mistral": "mistral",
    "GPT-OSS": "gpt-oss",
}

MODELS = {}  # diisi otomatis di bawah


def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return ""


@st.cache_data(ttl=600)
def daftar_model_gratis():
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=30)
        return sorted(m["id"] for m in r.json()["data"] if m["id"].endswith(":free"))
    except Exception:
        return []


def worker(nama, prompt, keys, status, hasil, max_retry):
    url, model, jenis = MODELS[nama]
    api_key = keys[jenis]
    for i in range(1, max_retry + 1):
        status[nama] = f"⏳ Mencoba ke-{i}/{max_retry}..."
        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=300,
            )
            if r.status_code == 200:
                teks = r.json()["choices"][0]["message"]["content"]
                if teks and teks.strip():
                    hasil[nama] = teks
                    status[nama] = "✅ Selesai"
                    return
                status[nama] = "⚠️ Jawaban kosong, retry..."
            elif r.status_code not in RETRY_CODES:
                status[nama] = f"❌ Error {r.status_code}: {r.text[:150]}"
                return
            else:
                status[nama] = f"⚠️ Status {r.status_code} (sibuk), retry..."
        except Exception as e:
            status[nama] = f"⚠️ {type(e).__name__}, retry..."
        time.sleep(min(2 ** i, 30))
    status[nama] = f"❌ Gagal total setelah {max_retry}x percobaan"


def buat_zip(hasil, prompt):
    buf = io.BytesIO()
    gabungan = f"# Prompt\n\n{prompt}\n\n---\n\n"
    with zipfile.ZipFile(buf, "w") as z:
        for nama, teks in hasil.items():
            md = f"# {nama} ({MODELS[nama][1]})\n\n{teks}\n"
            z.writestr(f"{nama}.md", md)
            gabungan += md + "\n---\n\n"
        z.writestr("semua_hasil.md", gabungan)
    return buf.getvalue()


st.set_page_config(page_title="Multi-AI Bola", layout="wide")
st.title("⚽ Multi-AI Analisis Bola")

# ---------- API KEY ----------
with st.expander("🔑 API Key", expanded=not get_secret("OR_KEY")):
    key_or = st.text_input("OpenRouter API Key", type="password",
                           value=get_secret("OR_KEY"))
    key_gemini = st.text_input("Google AI Studio (Gemini) API Key",
                               type="password", value=get_secret("GEMINI_KEY"))
keys = {"or": key_or.strip().strip('"'), "gemini": key_gemini.strip().strip('"')}
st.caption(
    f"OpenRouter key: {'✅ ' + keys['or'][:8] + '...' if keys['or'] else '❌ kosong'} | "
    f"Gemini key: {'✅ ' + keys['gemini'][:6] + '...' if keys['gemini'] else '❌ kosong'}"
)

# ---------- PILIH MODEL ----------
gratis = daftar_model_gratis()
with st.expander("⚙️ Pilih model (otomatis dari daftar gratis yang aktif)", expanded=True):
    gem = st.text_input("Model Gemini", value="gemini-3.8-flash")
    MODELS["Gemini"] = (GEMINI, gem.strip(), "gemini")

    if not gratis:
        st.warning("Gagal mengambil daftar model gratis OpenRouter. Refresh halaman.")
    else:
        st.caption(f"Ditemukan {len(gratis)} model gratis aktif di OpenRouter.")

    opsi = ["(tidak dipakai)"] + gratis
    cols = st.columns(2)
    for i, (nama, kw) in enumerate(SLOT.items()):
        cocok = [m for m in gratis if kw in m.lower()]
        idx = opsi.index(cocok[0]) if cocok else 0
        pilihan = cols[i % 2].selectbox(nama, opsi, index=idx, key=f"m_{nama}")
        if pilihan != "(tidak dipakai)":
            MODELS[nama] = (OPENROUTER, pilihan, "or")

# ---------- PROMPT ----------
prompt = st.text_area("Prompt analisis", height=250)
c1, c2 = st.columns(2)
pilih = c1.multiselect("AI yang dipakai", list(MODELS), default=list(MODELS))
max_retry = c2.slider("Maksimal retry per AI", 1, 10, 5)

if st.button("🚀 Kirim ke semua AI", type="primary"):
    if not prompt.strip() or not pilih:
        st.error("Prompt dan minimal 1 AI wajib dipilih.")
        st.stop()
    for n in pilih:
        if not keys[MODELS[n][2]]:
            st.error(f"API key untuk {n} belum diisi.")
            st.stop()

    status = {n: "🕐 Menunggu" for n in pilih}
    hasil = {}
    boxes = {n: st.empty() for n in pilih}

    ex = ThreadPoolExecutor(max_workers=len(pilih))
    futures = [ex.submit(worker, n, prompt, keys, status, hasil, max_retry)
               for n in pilih]
    def tampil(n):
        teks = "**" + n + "** (" + MODELS[n][1] + "): " + status[n]
        boxes[n].write(teks)

    while not all(f.done() for f in futures):
        for n in pilih:
            tampil(n)
        time.sleep(0.5)
    for n in pilih:
        tampil(n)
