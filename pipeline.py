import os
import json
import subprocess
from typing import Dict, TypedDict, Any, List, Optional
from dotenv import load_dotenv

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# --- 1. Pydantic Schema for OpenAI Structured Output ---
class Topic(BaseModel):
    title: str
    content: str

class CommonMistake(BaseModel):
    mistake: str
    why: str
    correct: str

class Example(BaseModel):
    title: str
    content: str
    code: str

class OptionalSections(BaseModel):
    realWorldApplications: List[str] = []
    commonMistakes: List[CommonMistake] = []
    proTips: List[str] = []
    examples: List[Example] = []
    conclusion: str = ""

class Diagram(BaseModel):
    title: str = ""
    description: str = ""
    plantuml: str = ""

class EducationalContent(BaseModel):
    topics: List[Topic]
    optionalSections: Optional[OptionalSections] = None
    diagram: Optional[Diagram] = None
    summary: str

# --- 2. State Definition ---
class PipelineState(TypedDict):
    topic: str
    submodule_title: str
    user_level: str
    context: str
    generated_json: EducationalContent | None
    input_file_path: str
    video_output_path: str

# --- 3. Prompt ---
def get_submodule_content_prompt(topic: str, submodule_title: str, user_level: str, context: str = "") -> str:
    """Generate rich educational content for a submodule."""
    level_guidance = {
        "beginner": "Use simple language, relatable analogies, and step-by-step explanations. Assume no prior knowledge.",
        "intermediate": "Assume foundational knowledge. Focus on practical applications, patterns, and connecting concepts.",
        "advanced": "Go deep into technical details, edge cases, best practices, and performance considerations."
    }.get(user_level.lower(), "Balance theory with practical examples at an intermediate level.")
    
    return f"""Create a comprehensive, engaging lesson on "{submodule_title}" as part of learning {topic}.

LEARNER LEVEL: {user_level}
{level_guidance}

{f"CONTEXT: {context}" if context else ""}

CRITICAL: Generate content in this EXACT JSON structure. Do NOT put content inside a "lesson" wrapper. 
The "topics" array MUST be at the root level, not nested inside anything else.

REQUIRED STRUCTURE:
{{
  "topics": [
    {{
      "title": "Clear topic heading",
      "content": "Rich markdown content with comprehensive explanations, make content engaging and easy to understand and gold standard quality, code examples, tips"
    }}
  ],
  "optionalSections": {{
    "realWorldApplications": ["Use case 1", "Use case 2"],
    "commonMistakes": [{{"mistake": "What they do wrong", "why": "Why it's wrong", "correct": "The right way"}}],
    "proTips": ["Expert tip 1", "Expert tip 2"],
    "examples": [{{"title": "Example name", "content": "Explanation", "code": "Code snippet wrapped in ```language triple backticks (e.g. ```yaml, ```sql, etc)"}}],
    "conclusion": "Motivating wrap-up"
  }},
  "diagram": {{
    "title": "Title describing what the diagram shows",
    "description": "Brief explanation of what this diagram illustrates and how it helps understand the concept",
    "plantuml": "@startuml\\n... PlantUML code ...\\n@enduml"
  }},
  "summary": "Concise summary of key takeaways"
}}

REQUIREMENTS:
1. Generate 3-5 topics in the topics array
2. Content should use markdown: headers (##, ###), bullet points, **bold**.
3. ANY config, yaml, sql, bash, or programming code MUST be wrapped in triple backticks (```yaml, ```sql, etc) inside the content.

OPTIONAL DIAGRAM - Include ONLY if it genuinely helps understanding:
- Include a "diagram" field ONLY when the concept can be better understood visually
- Skip for: simple definitions, or topics that don't benefit from visualization
- The diagram should illustrate CONCEPTUAL understanding
- Use PlantUML syntax: activity diagrams, mind maps, sequence diagrams, or component diagrams or any valid plantuml diagrams

QUALITY: Make it feel like learning from an expert mentor. Be thorough but engaging."""

# --- 4. Nodes ---
def generate_content(state: PipelineState) -> PipelineState:
    print(f"\n[1/3] Generating content for: {state['submodule_title']}...")
    llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
    structured_llm = llm.with_structured_output(EducationalContent)
    
    prompt = get_submodule_content_prompt(
        state["topic"],
        state["submodule_title"],
        state["user_level"],
        state["context"]
    )
    
    result = structured_llm.invoke(prompt)
    return {"generated_json": result}

def save_to_file(state: PipelineState) -> PipelineState:
    print("[2/3] Formatting and saving to text_creation/input.txt...")
    content = state["generated_json"]
    
    lines = []
    # 1. TITLE Slide
    lines.append("[TITLE]")
    lines.append(state["submodule_title"])
    lines.append("---")
    
    # 2. CONCEPT Slides
    for t in content.topics:
        lines.append("[CONCEPT]")
        lines.append(f"# {t.title}")
        lines.append(t.content)
        lines.append("---")
        
    # 3. CODE Slides
    if content.optionalSections and content.optionalSections.examples:
        for ex in content.optionalSections.examples:
            code_str = ex.code
            if code_str and len(code_str.strip()) > 0:
                lines.append("[CODE]")
                lines.append(f"# {ex.title if ex.title else 'Code Example'}")
                lines.append(ex.content)
                
                # Check if LLM forgot backticks
                if not code_str.strip().startswith("```"):
                    lines.append("```python")
                    lines.append(code_str)
                    lines.append("```")
                else:
                    lines.append(code_str)
                    
                lines.append("---")
                
    # 4. SUMMARY Slide
    lines.append("[SUMMARY]")
    lines.append("# Key Takeaways")
    lines.append(content.summary)
    if content.optionalSections and content.optionalSections.proTips:
        for tip in content.optionalSections.proTips:
            lines.append(f"- Pro Tip: {tip}")
    if content.optionalSections and content.optionalSections.conclusion:
        lines.append(f"- Conclusion: {content.optionalSections.conclusion}")
    
    output_path = os.path.join(os.path.dirname(__file__), "input.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    return {"input_file_path": output_path}

def trigger_video(state: PipelineState) -> PipelineState:
    import sys
    print(f"[3/3] Triggering Manim video generation (HD)...")
    video_making_dir = os.path.join(os.path.dirname(__file__), '..', 'video_making')
    cmd = [
        sys.executable, "-m", "manim", 
        "-pqh", "video_genration.py", "DynamicScene"
    ]
    subprocess.run(cmd, check=True, cwd=video_making_dir)
    return {"video_output_path": "video_making/media/videos/video_genration/1080p60/DynamicScene.mp4"}

# --- 5. Graph Assembly ---
workflow = StateGraph(PipelineState)
workflow.add_node("generate_content", generate_content)
workflow.add_node("save_to_file", save_to_file)
workflow.add_node("trigger_video", trigger_video)

workflow.add_edge(START, "generate_content")
workflow.add_edge("generate_content", "save_to_file")
workflow.add_edge("save_to_file", "trigger_video")
workflow.add_edge("trigger_video", END)

app = workflow.compile()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="Prometheus")
    parser.add_argument("--submodule", default="Define basic alert rules for CPU, Memory, and disk metrices.")
    parser.add_argument("--level", default="Beginner")
    
    args = parser.parse_args()
    
    initial_state = {
        "topic": args.topic,
        "submodule_title": args.submodule,
        "user_level": args.level,
        "context": "",
        "generated_json": None,
        "input_file_path": "",
        "video_output_path": ""
    }
    
    print("=== LangGraph Auto-Video Pipeline Started ===")
    app.invoke(initial_state)
    print("=== Pipeline Complete! ===")
