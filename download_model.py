
from pathlib import Path
import sys
import urllib.request

FILES = [
    (
        "qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
        "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
    ),
    (
        "qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf",
        "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf",
    ),
]

MODELS_DIR = Path(__file__).resolve().parent / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

def human_size(value):
    value = float(value)
    units = ["o", "Ko", "Mo", "Go", "To"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024

def download(name, url):
    dest = MODELS_DIR / name
    tmp = dest.with_suffix(dest.suffix + ".part")

    if dest.exists() and dest.stat().st_size > 10_000_000:
        print(f"[OK] Déjà présent : {dest.name} ({human_size(dest.stat().st_size)})")
        return

    print(f"\nTéléchargement : {name}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 GlobalExamBot/0.9.3.1"},
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 / total
                        print(f"\r{pct:6.2f}%  {human_size(downloaded)} / {human_size(total)}", end="", flush=True)
                    else:
                        print(f"\r{human_size(downloaded)} téléchargés", end="", flush=True)
        print()

        if tmp.stat().st_size < 10_000_000:
            raise RuntimeError("Fichier téléchargé anormalement petit")

        tmp.replace(dest)
        print(f"[OK] {dest.name} ({human_size(dest.stat().st_size)})")
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass
        raise

def main():
    print("=" * 57)
    print(" Téléchargement Qwen 2.5 7B Instruct GGUF Q4_K_M")
    print(" Python urllib - aucun curl nécessaire")
    print("=" * 57)
    print()
    print("ATTENTION : plusieurs Go seront téléchargés.")

    for index, (name, url) in enumerate(FILES, 1):
        print(f"\n--- Shard {index}/{len(FILES)} ---")
        download(name, url)

    print("\nTous les fichiers du modèle sont prêts dans :")
    print(MODELS_DIR)
    print("\nTu peux maintenant lancer test_local_llm.bat puis run.bat.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTéléchargement interrompu.")
        sys.exit(130)
    except Exception as exc:
        print(f"\nERREUR : {exc}")
        sys.exit(1)
