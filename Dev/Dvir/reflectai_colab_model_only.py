import json
import re
from typing import Literal

import gradio as gr
import torch
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
USE_REAL_MODEL = True
MAX_NEW_TOKENS = 320
TEMPERATURE = 0.1

SYSTEM_PROMPT = """
You are a communication reflection assistant.

You analyze one outgoing message before it is sent.

Return JSON only with this exact structure:
{
  "flagged": boolean,
  "severity": "none" | "low" | "medium" | "high",
  "category": "safe" | "rude" | "aggressive" | "insult" | "escalation",
  "reflection": string,
  "suggested_rewrite": string,
  "problematic_spans": [
    {
      "text": string,
      "label": "rude" | "aggressive" | "insult" | "threat" | "dismissive" | "escalation"
    }
  ]
}

Rules:
- Analyze the full meaning, tone, phrasing, and context of the message.
- Do not rely only on swear words or obvious insults.
- A message can be harmful even without profanity.
- If the message is safe, return:
  - flagged = false
  - severity = "none"
  - category = "safe"
  - problematic_spans = []
- If flagged, include the exact parts of the original message that caused concern.
- problematic_spans.text must be copied exactly from the original message, not paraphrased.
- Keep reflection short and educational.
- Keep suggested_rewrite close to the original meaning, but more respectful.
- Return JSON only.
""".strip()


class ProblemSpan(BaseModel):
    text: str
    label: Literal["rude", "aggressive", "insult", "threat", "dismissive", "escalation"]


class AnalysisResult(BaseModel):
    flagged: bool
    severity: Literal["none", "low", "medium", "high"]
    category: Literal["safe", "rude", "aggressive", "insult", "escalation"]
    reflection: str
    suggested_rewrite: str
    problematic_spans: list[ProblemSpan]


def extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return json.loads(match.group(0))


def safe_parse_result(text: str, original_message: str) -> AnalysisResult:
    try:
        data = extract_json(text)
        return AnalysisResult(**data)
    except Exception:
        return AnalysisResult(
            flagged=False,
            severity="none",
            category="safe",
            reflection="Analysis unavailable right now.",
            suggested_rewrite=original_message,
            problematic_spans=[],
        )


tokenizer = None
model = None


def load_model():
    global tokenizer, model

    if tokenizer is not None and model is not None:
        return "Model already loaded."

    if not USE_REAL_MODEL:
        return "USE_REAL_MODEL is False. Model analysis is disabled."

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        torch_dtype="auto",
        device_map="auto",
    )
    return f"Loaded {MODEL_NAME}"


def analyze_message_model(message: str) -> AnalysisResult:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f'Analyze this outgoing message and identify problematic spans exactly as written:\n"{message}"',
        },
    ]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs = tokenizer([text], return_tensors="pt")
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            temperature=TEMPERATURE,
            do_sample=False,
        )

    generated_ids = output_ids[:, inputs["input_ids"].shape[1]:]
    generated_text = tokenizer.batch_decode(
        generated_ids,
        skip_special_tokens=True,
    )[0]

    return safe_parse_result(generated_text, message)


def analyze_message(message: str) -> AnalysisResult:
    if not USE_REAL_MODEL:
        return AnalysisResult(
            flagged=False,
            severity="none",
            category="safe",
            reflection="Model analysis is disabled.",
            suggested_rewrite=message,
            problematic_spans=[],
        )

    if tokenizer is None or model is None:
        return AnalysisResult(
            flagged=False,
            severity="none",
            category="safe",
            reflection="Analysis unavailable right now.",
            suggested_rewrite=message,
            problematic_spans=[],
        )

    return analyze_message_model(message)


def format_spans(spans: list[ProblemSpan]) -> str:
    if not spans:
        return "Problematic spans: none"
    lines = ["Problematic spans:"]
    for span in spans:
        lines.append(f'- [{span.label}] "{span.text}"')
    return "\n".join(lines)


def process_send(message, chat_history, pending_original):
    message = (message or "").strip()
    chat_history = chat_history or []

    if not message:
        return (
            chat_history,
            message,
            gr.update(visible=False),
            "",
            "",
            pending_original,
        )

    result = analyze_message(message)

    if not result.flagged:
        chat_history = chat_history + [{"role": "user", "content": message}]
        return (
            chat_history,
            "",
            gr.update(visible=False),
            "",
            "",
            "",
        )

    reflection = (
        f"Flagged: {result.category} | Severity: {result.severity}\n\n"
        f"{result.reflection}\n\n"
        f"{format_spans(result.problematic_spans)}"
    )

    return (
        chat_history,
        message,
        gr.update(visible=True),
        reflection,
        result.suggested_rewrite,
        message,
    )


def use_suggestion(chat_history, suggestion):
    chat_history = chat_history or []
    suggestion = (suggestion or "").strip()
    if suggestion:
        chat_history = chat_history + [{"role": "user", "content": suggestion}]
    return (
        chat_history,
        "",
        gr.update(visible=False),
        "",
        "",
        "",
    )


def send_anyway(chat_history, pending_original):
    chat_history = chat_history or []
    pending_original = (pending_original or "").strip()
    if pending_original:
        chat_history = chat_history + [{"role": "user", "content": pending_original}]
    return (
        chat_history,
        "",
        gr.update(visible=False),
        "",
        "",
        "",
    )


def edit_message(pending_original):
    return (
        pending_original or "",
        gr.update(visible=False),
        "",
        pending_original or "",
    )


with gr.Blocks() as demo:
    gr.Markdown("# ReflectAI")
    gr.Markdown("Send-time reflection layer for digital communication.")

    chat_state = gr.State([])
    pending_original_state = gr.State("")

    chatbot = gr.Chatbot(label="Conversation", type="messages", height=350)
    message_box = gr.Textbox(label="Message", placeholder="Type a message here...", lines=4)
    send_btn = gr.Button("Send")

    with gr.Group(visible=False) as review_group:
        reflection_box = gr.Textbox(label="Reflection", interactive=False, lines=8)
        suggestion_box = gr.Textbox(label="Suggested rewrite", lines=4)
        with gr.Row():
            use_btn = gr.Button("Use suggestion")
            anyway_btn = gr.Button("Send anyway")
            edit_btn = gr.Button("Edit message")

    send_btn.click(
        fn=process_send,
        inputs=[message_box, chat_state, pending_original_state],
        outputs=[chatbot, message_box, review_group, reflection_box, suggestion_box, pending_original_state],
    ).then(
        fn=lambda chat: chat,
        inputs=[chatbot],
        outputs=[chat_state],
    )

    use_btn.click(
        fn=use_suggestion,
        inputs=[chat_state, suggestion_box],
        outputs=[chatbot, message_box, review_group, reflection_box, suggestion_box, pending_original_state],
    ).then(
        fn=lambda chat: chat,
        inputs=[chatbot],
        outputs=[chat_state],
    )

    anyway_btn.click(
        fn=send_anyway,
        inputs=[chat_state, pending_original_state],
        outputs=[chatbot, message_box, review_group, reflection_box, suggestion_box, pending_original_state],
    ).then(
        fn=lambda chat: chat,
        inputs=[chatbot],
        outputs=[chat_state],
    )

    edit_btn.click(
        fn=edit_message,
        inputs=[pending_original_state],
        outputs=[message_box, review_group, reflection_box, pending_original_state],
    )

print(load_model())
demo.launch(debug=True)
