import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from evaluator import evaluate_equations_images, evaluate_equations_text

# Load environment variables from .env
load_dotenv()

# Page configuration - must be before any other Streamlit UI calls
st.set_page_config(
    page_title="Equation Comparator & Marks Allocator",
    page_icon="📐",
    layout="wide"
)

# Sidebar for settings
with st.sidebar:
    st.header("⚙️ Configuration")
    
    env_api_key = os.getenv("GROQ_API_KEY", "")
    api_key_input = st.text_input(
        "Groq API Key",
        value=env_api_key,
        type="password",
        help="Reads from .env by default or enter your Groq API key directly."
    )
    
    input_mode = st.radio(
        "Input Mode",
        options=["🖼️ Images (Rubric & Answer)", "✍️ Text (Plain Equations)"],
        index=0
    )
    
    if "Images" in input_mode:
        model_options = [
            "qwen/qwen3.6-27b",
            "qwen-2.5-32b",
            "Custom..."
        ]
    else:
        model_options = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "qwen-qwq-32b",
            "mixtral-8x7b-32768",
            "Custom..."
        ]
        
    selected_model = st.selectbox(
        "Model",
        options=model_options,
        index=0,
        help="Select the Groq Vision / LLM model to use for comparison."
    )
    
    if selected_model == "Custom...":
        model_choice = st.text_input(
            "Custom Model ID",
            value="qwen/qwen3.6-27b",
            help="Enter any valid Groq model ID."
        )
    else:
        model_choice = selected_model

    
    st.markdown("---")
    st.markdown(
        """
        ### ℹ️ How it works:
        1. **Image Mode**: Upload the Rubric image and Student Answer image.
        2. **Vision LLM**: Groq Vision reads the equations, verifies steps & math equivalence, and allocates marks.
        3. **Output**: View the calculated total score and step-wise grading table.
        """
    )

# Main Title & Subheading
st.title("📐 Equation Comparator & Marks Allocator")
st.caption("Automated mathematical step-by-step grading powered by Groq Vision LLMs.")

# Pre-defined default examples for text mode
DEFAULT_RUBRIC = """Step 1: 2*x = 6
Marks: 1

Step 2: x = 3
Marks: 1

Final Answer: x = 3
Marks: 1"""

DEFAULT_STUDENT_ANSWER = """2*x = 6
x = 3
x = 3"""

results_placeholder = None

if "Images" in input_mode:
    # Two-column layout for Image Uploads
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("1. 📋 Marking Rubric Image")
        rubric_file = st.file_uploader(
            "Upload image of the marking rubric:",
            type=["png", "jpg", "jpeg", "webp"],
            key="rubric_img_uploader"
        )
        if rubric_file:
            st.image(rubric_file, caption="Rubric Image Preview", use_container_width=True)

    with col2:
        st.subheader("2. ✍️ Student Answer Image")
        student_file = st.file_uploader(
            "Upload image of student's written equations:",
            type=["png", "jpg", "jpeg", "webp"],
            key="student_img_uploader"
        )
        if student_file:
            st.image(student_file, caption="Student Answer Image Preview", use_container_width=True)

    # Evaluate Button for Image Mode
    st.markdown("<br>", unsafe_allow_html=True)
    evaluate_btn = st.button("🚀 Evaluate Answer from Images", type="primary", use_container_width=True)

    if evaluate_btn:
        if not api_key_input.strip():
            st.error("⚠️ Groq API Key is missing. Please provide it in the sidebar or in your `.env` file.")
        elif not rubric_file:
            st.warning("⚠️ Please upload a marking rubric image.")
        elif not student_file:
            st.warning("⚠️ Please upload a student answer image.")
        else:
            with st.spinner("Processing images with Groq Vision LLM..."):
                rubric_bytes = rubric_file.getvalue()
                student_bytes = student_file.getvalue()
                
                rubric_mime = rubric_file.type or "image/png"
                student_mime = student_file.type or "image/png"

                success, result_data, error_msg = evaluate_equations_images(
                    rubric_image_bytes=rubric_bytes,
                    student_image_bytes=student_bytes,
                    rubric_mime=rubric_mime,
                    student_mime=student_mime,
                    api_key=api_key_input,
                    model_name=model_choice
                )

            if not success:
                st.error(f"❌ {error_msg}")
            else:
                st.markdown("---")
                st.subheader("📊 Evaluation Results")

                total_marks = result_data.get("total_marks", 0)
                max_marks = result_data.get("maximum_marks", 0)

                score_col1, score_col2 = st.columns([1, 3])
                with score_col1:
                    st.metric(
                        label="TOTAL SCORE",
                        value=f"{total_marks} / {max_marks}",
                        delta=f"{round((total_marks / max_marks * 100) if max_marks else 0)}%"
                    )

                table_rows = []
                for item in result_data.get("results", []):
                    is_correct = item.get("correct", False)
                    result_label = "✅ Correct" if is_correct else "❌ Incorrect"
                    marks_str = f"{item.get('marks_awarded', 0)} / {item.get('max_marks', 1)}"
                    
                    table_rows.append({
                        "Rubric Step": item.get("rubric_step", ""),
                        "Student Step": item.get("student_step", ""),
                        "Result": result_label,
                        "Marks": marks_str,
                        "Reason": item.get("reason", "")
                    })

                df = pd.DataFrame(table_rows)

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )

                with st.expander("🔍 View Raw JSON Output"):
                    st.json(result_data)

else:
    # Text Mode
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("1. 📋 Marking Rubric")
        rubric_text = st.text_area(
            label="Enter marking rubric with steps and marks:",
            value=DEFAULT_RUBRIC,
            height=220,
            placeholder="Step 1: 2*x = 6\nMarks: 1\n\nStep 2: x = 3\nMarks: 1"
        )

    with col2:
        st.subheader("2. ✍️ Student Answer")
        student_text = st.text_area(
            label="Enter student's written equations/steps:",
            value=DEFAULT_STUDENT_ANSWER,
            height=220,
            placeholder="2*x = 6\nx = 3\nx = 3"
        )

    evaluate_btn = st.button("🚀 Evaluate Answer from Text", type="primary", use_container_width=True)

    if evaluate_btn:
        if not api_key_input.strip():
            st.error("⚠️ Groq API Key is missing. Please provide it in the sidebar or in your `.env` file.")
        elif not rubric_text.strip():
            st.warning("⚠️ Please provide a marking rubric.")
        elif not student_text.strip():
            st.warning("⚠️ Please provide student equations to evaluate.")
        else:
            with st.spinner("Evaluating equations with LLM..."):
                success, result_data, error_msg = evaluate_equations_text(
                    rubric=rubric_text,
                    student_answer=student_text,
                    api_key=api_key_input,
                    model_name=model_choice
                )

            if not success:
                st.error(f"❌ {error_msg}")
            else:
                st.markdown("---")
                st.subheader("📊 Evaluation Results")

                total_marks = result_data.get("total_marks", 0)
                max_marks = result_data.get("maximum_marks", 0)

                score_col1, score_col2 = st.columns([1, 3])
                with score_col1:
                    st.metric(
                        label="TOTAL SCORE",
                        value=f"{total_marks} / {max_marks}",
                        delta=f"{round((total_marks / max_marks * 100) if max_marks else 0)}%"
                    )

                table_rows = []
                for item in result_data.get("results", []):
                    is_correct = item.get("correct", False)
                    result_label = "✅ Correct" if is_correct else "❌ Incorrect"
                    marks_str = f"{item.get('marks_awarded', 0)} / {item.get('max_marks', 1)}"
                    
                    table_rows.append({
                        "Rubric Step": item.get("rubric_step", ""),
                        "Student Step": item.get("student_step", ""),
                        "Result": result_label,
                        "Marks": marks_str,
                        "Reason": item.get("reason", "")
                    })

                df = pd.DataFrame(table_rows)

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )

                with st.expander("🔍 View Raw JSON Output"):
                    st.json(result_data)
