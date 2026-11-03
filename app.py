import streamlit as st
import requests, time, io, zipfile
from concurrent.futures import ThreadPoolExecutor

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
RETRY_CODES = {408, 429, 500, 502, 503, 504}

# nama AI -> kata kunci pencari model gratis
SLOT = {
    "DeepSeek": ["deepseek"],
    "GLM": ["glm"],
    "Kimi": ["kimi", "moonshot"],
    "Qwen": ["qwen"],
    "Llama": ["llama"],
    "Mistral": ["mistral"],
    "GPT-OSS": ["gpt-oss"],
}

KOSONG = "(tidak dipakai)"


def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return ""


@st.cache_data(ttl=600)
def daftar_model_gratis():
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=30)
        data = r.json()["data"]
        return sorted(m["id"] for m in data if m["id"].endswith(":free"))
    except Exception:
        return []


@st.cache_data(ttl=600)
def daftar_model_gemini(key):
    if not key:
        return []
    try:
        r = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": key, "pageSize": 200},
            timeout=30,
        )
        out = []
        buang = ["image", "tts", "live", "audio", "embedding",
                 "thinking", "robotics", "computer"]
        for m in r.json().get("models", []):
            nm = m["name"].replace("models/", "")
            metode = m.get("supportedGenerationMethods", [])
            if "generateContent" in metode and "flash" in nm:
                if not any(x in nm for x in buang):
                    out.append(nm)
        out.sort(reverse=True)
        out.sort(key=lambda x: ("lite" in x, "preview" in x or "exp" in x))
        return out
    except Exception:
        return []


def coba_satu_model(url, model, api_key, prompt, max_retry, nama, status):
    err = ""
    for i in range(1, max_retry + 1):
        status[nama] = "⏳ " + model + " (percobaan " + str(i) + "/" + str(max_retry) + ")"
        try:
            r = requests.post(
                url,
                headers={"Authorization": "Bearer " + api_key},
                json={"model": model,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=300,
            )
            if r.status_code == 200:
                teks = r.json()["choices"][0]["message"]["content"]
                if teks and teks.strip():
                    return teks, ""
                err = "jawaban kosong"
            elif r.status_code in RETRY_CODES:
                err = "status " + str(r.status_code) + " (sibuk)"
            else:
                return None, "error " + str(r.status_code) + ": " + r.text[:120]
        except Exception as e:
            err = type(e).__name__
        status[nama] = "⚠️ " + model + ": " + err + ", retry..."
        time.sleep(min(2 ** i, 20))
    return None, "gagal " + str(max_retry) + "x (" + err + ")"


def worker(nama, prompt, keys, status, hasil, dipakai, max_retry, fallback):
    url, kandidat, jenis = MODELS[nama]
    api_key = keys[jenis]
    if not fallback:
        kandidat = kandidat[:1]
    log = []
    for model in kandidat:
        teks, err = coba_satu_model(url, model, api_key, prompt,
                                    max_retry, nama, status)
        if teks:
            hasil[nama] = teks
            dipakai[nama] = model
            if log:
                status[nama] = "✅ Selesai pakai " + model + " (setelah ganti model)"
            else:
                status[nama] = "✅ Selesai (" + model + ")"
            return
        log.append(model + " -> " + err)
        status[nama] = "🔄 " + model + " gagal, coba model lain..."
    status[nama] = "❌ Semua model gagal. Terakhir: " + log[-1]


def isi_md(nama, model, teks):
    return "# " + nama + " (" + model + ")\n\n" + teks + "\n"


def buat_file_md(nama_terpilih, hasil, dipakai, prompt):
    """Return (dict nama_file -> isi, bytes zip)."""
    files = {}
    gabungan = "# Prompt\n\n" + prompt + "\n\n---\n\n"
    for nama in nama_terpilih:
        md = isi_md(nama, dipakai[nama], hasil[nama])
        files[nama + ".md"] = md
        gabungan += md + "\n---\n\n"
    files["semua_hasil.md"] = gabungan
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for fname, isi in files.items():
            z.writestr(fname, isi)
    return files, buf.getvalue()


st.set_page_config(page_title="Multi-AI Bola", layout="wide")
st.title("⚽ Multi-AI Analisis Bola")

# ---------- API KEY ----------
with st.expander("🔑 API Key", expanded=not get_secret("OR_KEY")):
    key_or = st.text_input("OpenRouter API Key", type="password",
                           value=get_secret("OR_KEY"))
    key_gemini = st.text_input("Google AI Studio (Gemini) API Key",
                               type="password", value=get_secret("GEMINI_KEY"))
keys = {"or": key_or.strip().strip('"'),
        "gemini": key_gemini.strip().strip('"')}

ket_or = ("✅ " + keys["or"][:8] + "...") if keys["or"] else "❌ kosong"
ket_gem = ("✅ " + keys["gemini"][:6] + "...") if keys["gemini"] else "❌ kosong"
st.caption("OpenRouter key: " + ket_or + " | Gemini key: " + ket_gem)

# ---------- AUTO PILIH MODEL ----------
MODELS = {}  # nama -> (url, [daftar kandidat], jenis_key)

gratis = daftar_model_gratis()
gemini_list = daftar_model_gemini(keys["gemini"])

with st.expander("⚙️ Model terpilih otomatis (bisa diubah manual)", expanded=False):
    if gratis:
        st.caption("Ditemukan " + str(len(gratis)) + " model gratis aktif di OpenRouter.")
    else:
        st.warning("Gagal mengambil daftar model gratis OpenRouter. Refresh halaman.")

    if gemini_list:
        st.caption("Ditemukan " + str(len(gemini_list)) + " model Gemini flash.")
        pil_gem = st.selectbox("Gemini", gemini_list, index=0, key="m_Gemini")
        kand_gem = [pil_gem] + [m for m in gemini_list if m != pil_gem]
    else:
        st.caption("Daftar model Gemini belum terbaca (cek key Gemini). Pakai nama manual:")
        manual = st.text_input("Gemini", value="gemini-3.8-flash", key="m_Gemini_manual")
        kand_gem = [manual.strip()]
    MODELS["Gemini"] = (GEMINI, kand_gem, "gemini")

    opsi = [KOSONG] + gratis
    cols = st.columns(2)
    for i, (nama, kws) in enumerate(SLOT.items()):
        cocok = [m for m in gratis if any(k in m.lower() for k in kws)]
        cocok.sort(reverse=True)
        idx = opsi.index(cocok[0]) if cocok else 0
        pilihan = cols[i % 2].selectbox(nama, opsi, index=idx, key="m_" + nama)
        if pilihan != KOSONG:
            urutan = [pilihan] + [m for m in cocok if m != pilihan]
            MODELS[nama] = (OPENROUTER, urutan, "or")

# ---------- PROMPT ----------
prompt = st.text_area("Prompt analisis", height=250)
c1, c2 = st.columns(2)
pilih = c1.multiselect("AI yang dipakai", list(MODELS), default=list(MODELS))
max_retry = c2.slider("Maksimal retry per model", 1, 10, 3)
fallback = st.checkbox("Auto-ganti ke model gratis lain kalau model gagal", value=True)

if st.button("🚀 Kirim ke semua AI", type="primary"):
    if not prompt.strip() or not pilih:
        st.error("Prompt dan minimal 1 AI wajib dipilih.")
        st.stop()
    for n in pilih:
        if not keys[MODELS[n][2]]:
            st.error("API key untuk " + n + " belum diisi.")
            st.stop()

    status = {n: "🕐 Menunggu" for n in pilih}
    hasil = {}
    dipakai = {}
    boxes = {n: st.empty() for n in pilih}

    def tampil(n):
        boxes[n].write("**" + n + "**: " + status[n])

    ex = ThreadPoolExecutor(max_workers=len(pilih))
    futures = [ex.submit(worker, n, prompt, keys, status, hasil,
                         dipakai, max_retry, fallback) for n in pilih]

    while not all(f.done() for f in futures):
        for n in pilih:
            tampil(n)
        time.sleep(0.5)
    for n in pilih:
        tampil(n)

    gagal = [n for n in pilih if n not in hasil]
    if gagal:
        st.warning("AI yang gagal: " + ", ".join(gagal))
    else:
        st.success("Semua AI berhasil! 🎉")

    # simpan hasil sebagai TEKS dulu (belum jadi file)
    st.session_state["hasil"] = hasil
    st.session_state["dipakai"] = dipakai
    st.session_state["prompt_terakhir"] = prompt
    st.session_state["run_id"] = st.session_state.get("run_id", 0) + 1
    st.session_state.pop("md_files", None)
    st.session_state.pop("md_zip", None)

# ---------- TAMPILKAN HASIL SEBAGAI TEKS ----------
if st.session_state.get("hasil"):
    hasil_s = st.session_state["hasil"]
    dipakai_s = st.session_state["dipakai"]
    rid = str(st.session_state.get("run_id", 0))

    st.divider()
    st.subheader("📝 Hasil (teks)")
    mode = st.radio("Tampilan", ["Teks biasa (mudah di-copy)", "Tampilan rapi (markdown)"],
                    horizontal=True)

    for nama, teks in hasil_s.items():
        with st.expander("📄 " + nama + " (" + dipakai_s[nama] + ")", expanded=True):
            if mode.startswith("Teks biasa"):
                st.text_area("hasil " + nama, value=teks, height=300,
                             key="ta_" + nama + "_" + rid,
                             label_visibility="collapsed")
            else:
                st.markdown(teks)

    # ---------- CONVERT KE .MD (OPSIONAL) ----------
    st.divider()
    st.subheader("📁 Convert ke file .md (opsional)")
    conv = st.multiselect("AI yang mau di-convert", list(hasil_s),
                          default=list(hasil_s), key="conv_" + rid)

    if st.button("📄 Convert ke file .md"):
        if not conv:
            st.error("Pilih minimal 1 AI untuk di-convert.")
        else:
            files, zip_bytes = buat_file_md(conv, hasil_s, dipakai_s,
                                            st.session_state["prompt_terakhir"])
            st.session_state["md_files"] = files
            st.session_state["md_zip"] = zip_bytes

    if st.session_state.get("md_files"):
        st.success("File .md siap diunduh:")
        st.download_button("⬇️ Download semua (.zip)",
                           st.session_state["md_zip"],
                           file_name="hasil_analisis.zip",
                           key="dl_zip_" + rid)
        for fname, isi in st.session_state["md_files"].items():
            st.download_button("⬇️ " + fname, isi, file_name=fname,
                               mime="text/markdown",
                               key="dl_" + fname + "_" + rid)
