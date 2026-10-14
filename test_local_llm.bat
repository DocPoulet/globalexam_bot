@echo off
title GlobalExam Bot - Test LLM local

if not exist venv\Scripts\python.exe (
    echo Venv absent. Lance install.bat.
    pause
    exit /b 1
)

call venv\Scripts\activate

python -c "from llama_cpp import Llama; p=r'models\qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf'; print('Chargement:',p); llm=Llama(model_path=p,n_ctx=512,n_threads=4,n_gpu_layers=0,verbose=False); r=llm.create_chat_completion(messages=[{'role':'user','content':'Return only JSON: {\"ok\":true}'}],max_tokens=32,temperature=0); print(r['choices'][0]['message']['content'])"

pause
