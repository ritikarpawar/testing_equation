# Equation Comparator & Marks Allocator Prototype (Vision & Text)

A lightweight prototype that compares student mathematical steps (from **Images** or **Text**) against a marking rubric and allocates marks using Groq's Vision LLMs via LangChain.

---

## 🎯 Features
- **🖼️ Image Inputs (Primary):** Upload images of the **Marking Rubric** and **Student Answer** with live image preview.
- **✍️ Text Mode (Optional):** Supports direct text input for testing plain equations.
- **Multimodal Groq Vision:** Uses `llama-3.2-11b-vision-preview` or `llama-3.2-90b-vision-preview` to inspect handwritten/typed equations and verify mathematical equivalence.
- **Strict Marks Validation:**
  - `marks_awarded <= max_marks` per step.
  - No negative marks.
  - Recalculates total score arithmetic so `total_marks <= maximum_marks`.
- **Streamlit Interface:** Total score metric, breakdown table, and optional raw JSON inspection.

---

## 📂 Project Structure

```
equation_comparator/
├── app.py              # Streamlit UI with Image & Text inputs
├── evaluator.py        # Vision prompt, Groq Multimodal call, JSON parsing & validation
├── .env                # Local environment file for GROQ_API_KEY
├── .env.example        # Environment variable template
├── requirements.txt    # Minimal dependencies
└── README.md           # Documentation and quickstart
```

---

## 🚀 Quickstart Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Groq API Key
Add your Groq API key in `.env`:
```env
GROQ_API_KEY=gsk_your_actual_groq_api_key
```
*(Or enter it directly in the Streamlit sidebar).*

### 3. Run the Application
```bash
streamlit run app.py
```

Open your browser at `http://localhost:8501`.
