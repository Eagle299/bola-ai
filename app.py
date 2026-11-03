import streamlit as st
import requests, time, io, zipfile
from concurrent.futures import ThreadPoolExecutor

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

# nama: (url, model, jenis_key)
# Nama model gratis sering berubah. Cek di openrouter.ai/models (filter: Free)
MODELS = {
    "Gemini":   (GEMINI, "gemini-2.5-flash", "gemini"),
    "DeepSeek": (OPENROUTER, "deepseek/deepseek-r1:free", "or"),
    "GLM":      (OPENROUTER, "z-ai/glm-4.5-air:free", "or"),
    "Kimi":     (OPENROUTER, "moonshotai/kimi-k2:free", "or"),
    "Qwen":     (OPENROUTER, "qwen/qwen3-235b-a22b:free", "or"),
    "Llama":    (OPENROUTER, "meta-llama/llama-3.3-70b-instruct:free", "or"),
    "Mistral":  (OPENROUTER, "mistralai/mistral-small-3.2-24b-instruct:free", "or"),
}

RETRY_CODES = {408, 429, 500, 502, 503, 504}


def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return ""


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

with st.expander("🔑 API Key", expanded=not get_secret("OR_KEY")):
    key_or = st.text_input("OpenRouter API Key", type="password",
                           value=get_secret("OR_KEY"))
    key_gemini = st.text_input("Google AI Studio (Gemini) API Key",
                               type="password", value=get_secret("GEMINI_KEY"))
keys = {"or": key_or, "gemini": key_gemini}

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

    while not all(f.done() for f in futures):
        for n in pilih:
            boxes[n].write(f"**{n}**: {status[n]}")
        time.sleep(0.5)
    for n in pilih:
        boxes[n].write(f"**{n}**: {status[n]}")

    gagal = [n for n in pilih if n not in hasil]
    if gagal:
        st.warning(f"AI yang gagal: {', '.join(gagal)}")
    else:
        st.success("Semua AI berhasil! 🎉")

    st.session_state["hasil"] = hasil
    st.session_state["zip"] = buat_zip(hasil, prompt)

if "zip" in st.session_state:
    st.download_button("⬇️ Download semua (.zip berisi file .md)",
                       st.session_state["zip"], file_name="hasil_analisis.zip")
    for nama, teks in st.session_state["hasil"].items():
        with st.expander(f"📄 {nama}"):
            st.markdown(teks)
