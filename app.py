import markdown
import gradio as gr
import yaml
import requests
import os
import json
from bs4 import BeautifulSoup
import html

# 读取 config.yaml 配置文件
def load_config():
    with open("config.yaml", "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    return config

config = load_config()
models = config.get("models", [])
os.environ["YOUR_API_KEY"] = config.get("YOUR_API_KEY")
API_URL = config.get("API_URL")

SYSTEM_MESSAGE = {"role": "system", "content": "You are a helpful assistant."}

def parse_line(line):
    try:
        if line.startswith("data: "):
            json_str = line[6:].strip()
        else:
            json_str = line.strip()
            
        data = json.loads(json_str)
        
        if "data" in data:
            choices = data["data"].get("choices", [])
        else:
            choices = data.get("choices", [])
            
        if choices and len(choices) > 0:
            delta = choices[0].get("delta", {})
            content = delta.get("content", "")
            return content
            
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}, 原始数据: {line}")
    except Exception as e:
        print(f"其他错误: {e}, 原始数据: {line}")
    
    return None

def send_chat_stream(model, messages, temperature, max_tokens):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ['YOUR_API_KEY']}"
    }

    formatted_messages = [SYSTEM_MESSAGE]
    formatted_messages.extend([msg for msg in messages if msg["role"] != "system"])

    payload = {
        "model": model,
        "messages": formatted_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True
    }

    try:
        with requests.post(API_URL, headers=headers, json=payload, stream=True) as response:
            response.encoding = 'utf-8'
            if response.status_code == 200:
                for line in response.iter_lines(decode_unicode=True):
                    if not line or line.strip() == "":
                        continue
                    if line.strip() == "[DONE]":
                        return
                    content = parse_line(line)
                    if content:
                        yield content
            else:
                yield f"Error: {response.status_code}, {response.text}"
    except requests.exceptions.RequestException as e:
        yield f"[请求错误: {str(e)}]"

css =""" 
#title {
    text-align: center;
    padding: 0.6rem;
    background: linear-gradient(90deg, #4b6cb7 0%, #182848 100%);
    color: white;
    font-size: 1.5rem;
    font-weight: bold;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    animation: glow 2s ease-in-out infinite alternate;
    margin: 0;
}

@keyframes glow {
    from {
        box-shadow: 0 0 5px #4b6cb7, 0 0 10px #4b6cb7, 0 0 15px #4b6cb7;
    }
    to {
        box-shadow: 0 0 10px #182848, 0 0 20px #182848, 0 0 30px #182848;
    }
}

#chat-history {
    height: 60vh;
    overflow-y: auto;
    box-shadow: 0px -2px 8px rgba(0, 0, 0, 0.2);
    border-radius: 8px;
    margin-top: 1rem;
    padding: 0.5rem;
    font-size: 0.9rem;
    font-family: Arial, sans-serif;
    background-color: white;
}

.message {
    margin: 0.5rem 0;
    padding: 0.8rem;
    border-radius: 8px;
    max-width: 85%;
    word-wrap: break-word;
}

.user-message {
    background-color: rgb(93, 92, 222);
    color: white;
    margin-left: auto;
}

.assistant-message {
    background-color: rgb(247, 247, 247);
    color: black;
}

#input-container {

    display: flex;
    gap: 0.5rem;
    padding: 0.5rem;
    height="100px"
    width: 100%;
    background-color: white;
    box-shadow: 0px -2px 5px rgba(0, 0, 0, 0.1);
}

#user-input {
    max-height: 80px;
    overflow-y: auto;
    resize: none;
}

#send-btn {
    width: 100px;
}

.config-column {
    max-width: 200px !important;
    padding: 0.8rem;
}




"""

# 修改：处理换行符和特殊符号
def format_message(role, content):
    css_class = "user-message" if role == "user" else "assistant-message"
    # 使用 HTML 标签格式化内容，确保换行符等符号能显示
    formatted_content = html.escape(content).replace("\n", "<br>")
    return f'<div class="message {css_class}">{formatted_content}</div>'

def parse_chat_history(chat_html):
    soup = BeautifulSoup(chat_html, "html.parser")
    messages = []
    for message in soup.find_all(class_="message"):
        content = message.text.strip()
        if "user-message" in message["class"]:
            messages.append({"role": "user", "content": content})
        elif "assistant-message" in message["class"]:
            messages.append({"role": "assistant", "content": content})
    return messages

def chat_interface():
    with gr.Blocks(css=css) as demo:
        gr.HTML('<h2 id="title">Bob的AI小屋</h2>')

        with gr.Row():
            with gr.Column(scale=1, elem_classes="config-column"):
                gr.Markdown("## 配置选项")
                model = gr.Dropdown(label="模型", choices=models, value=models[0])
                temperature = gr.Slider(label="采样温度 (0-2)", minimum=0, maximum=2, step=0.1, value=0.7)
                max_tokens = gr.Slider(label="最大令牌数", minimum=1, maximum=8192, step=1, value=2048)
                clear_button = gr.Button("清除历史", elem_id="clear-btn")

            with gr.Column(scale=5):
                chatbot = gr.HTML(elem_id="chat-history")
                with gr.Row(elem_id="input-container", equal_height=True):
                    with gr.Column(scale=9, min_width=0):  # 输入框占比90%
                        user_input = gr.Textbox(
                            label="", 
                            placeholder="输入您的消息...",
                            elem_id="user-input"
                        )
                    with gr.Column(scale=1, min_width=0):  # 发送按钮占比10%
                        send_button = gr.Button("发送", elem_id="send-btn")

        def update_chat(model, temperature, max_tokens, chat_history, user_input):
            if not user_input.strip():
                return chat_history, ""
            
            current_html = chat_history or ""
            
            # 将当前用户消息加入HTML
            user_message_html = format_message("user", user_input)
            current_html += user_message_html  # 更新HTML历史

            # 解析现有聊天历史，不包含本次用户输入
            messages = parse_chat_history(chat_history)
            
            # 添加当前用户输入到 messages
            messages.append({"role": "user", "content": user_input})

            # 生成助手消息
            assistant_message = ""
            for chunk in send_chat_stream(model, messages, temperature, max_tokens):
                assistant_message += chunk
                temp_html = current_html + format_message("assistant", assistant_message)
                yield temp_html, ""

        def clear_chat_history():
            """清空聊天历史"""
            return ""

        user_input.submit(
            update_chat,
            inputs=[model, temperature, max_tokens, chatbot, user_input],
            outputs=[chatbot, user_input]
        )
        
        send_button.click(
            update_chat,
            inputs=[model, temperature, max_tokens, chatbot, user_input],
            outputs=[chatbot, user_input]
        )
        
        clear_button.click(
            clear_chat_history, 
            inputs=[], 
            outputs=[chatbot]
        )

    return demo

demo = chat_interface()
demo.launch()



