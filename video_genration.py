from manim import *
from manim_voiceover import VoiceoverScene
from manim_voiceover.services.gtts import GTTSService
import re
import textwrap

# ── Universal Markdown Parser ─────────────────────────────────────────────────

def guess_code_language(text):
    text_lower = text.lower()
    if "select " in text_lower or "insert " in text_lower or "update " in text_lower:
        return "sql"
    if "apiversion:" in text_lower or "kind:" in text_lower or "metadata:" in text_lower:
        return "yaml"
    if "kubectl " in text_lower or "docker " in text_lower or "npm " in text_lower:
        return "bash"
    if "def " in text or "class " in text or "import " in text or "{}" in text:
        return "python"
    return None

def parse_markdown_blocks(raw_text):
    """
    Parses a raw Markdown string into structured typed blocks.
    Supports: h1, h2, h3, code, bullet, paragraph
    """
    blocks = []
    lines = raw_text.splitlines()
    current_paragraph = []
    
    def flush_paragraph():
        if current_paragraph:
            # Re-join keeping raw indentation just in case guess_code_language hits it
            raw_node_text = "\n".join(current_paragraph).rstrip()
            # stripped text for paragraphs
            text = " ".join([l.strip() for l in current_paragraph]).strip()
            
            if text:
                lang = guess_code_language(raw_node_text)
                # If we suspect it's code and it's multiple lines, wrap it.
                if lang and len(current_paragraph) > 1 and not text.startswith("["):
                    blocks.append({"type": "code", "language": lang, "content": raw_node_text})
                else:
                    blocks.append({"type": "paragraph", "text": text})
            current_paragraph.clear()

    in_code_block = False
    code_lines = []
    code_lang = "python"
    
    for line in lines:
        stripped = line.strip()
        
        is_fence = stripped.startswith("```")
        is_opening_fence = is_fence and stripped[3:].strip() != ""  # e.g. ```yaml
        is_closing_fence = stripped == "```"                         # exactly ```
        
        if is_fence:
            if not in_code_block and (is_opening_fence or is_closing_fence):
                # Opening: ```lang
                flush_paragraph()
                in_code_block = True
                code_lang = stripped[3:].strip()
                if not code_lang:
                    code_lang = "python"
                code_lines = []
            elif in_code_block and is_closing_fence:
                # Closing: exactly ```
                in_code_block = False
                blocks.append({"type": "code", "language": code_lang, "content": "\n".join(code_lines)})
        elif in_code_block:
            # Preservation of Left Indentation! Extremely critical for YAML and Python
            code_lines.append(line.rstrip())
        else:
            if stripped.startswith("# "):
                flush_paragraph()
                blocks.append({"type": "h1", "text": stripped[2:].strip()})
            elif stripped.startswith("## "):
                flush_paragraph()
                blocks.append({"type": "h2", "text": stripped[3:].strip()})
            elif stripped.startswith("### "):
                flush_paragraph()
                blocks.append({"type": "h3", "text": stripped[4:].strip()})
            elif stripped.startswith("- ") or stripped.startswith("* "):
                flush_paragraph()
                blocks.append({"type": "bullet", "text": stripped[2:].strip()})
            elif not stripped:
                flush_paragraph()
            else:
                # Add exactly as is, keeping raw text
                current_paragraph.append(line)
        
    if in_code_block: # Handle unclosed block at EOF
        blocks.append({"type": "code", "language": code_lang, "content": "\n".join(code_lines)})
        
    flush_paragraph()
    return blocks

def parse_input(filepath="../text_creation/input.txt"):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    raw_sections = re.split(r"\n\s*---+\s*\n", content)
    sections = []

    for raw in raw_sections:
        raw = raw.strip()
        if not raw:
            continue
            
        lines = raw.splitlines()
        first_line = lines[0].strip()
        mode = "concept"
        if first_line.startswith("[") and first_line.endswith("]"):
            mode_match = re.search(r"\[(.*?)\]", first_line)
            if mode_match:
                mode = mode_match.group(1).lower()
            raw_text = "\n".join(lines[1:])
        else:
            raw_text = raw

        blocks = parse_markdown_blocks(raw_text)
        
        # Ensure title parsing for Voiceover
        title = None
        for b in blocks:
            if b["type"] in ["h1", "h2", "h3"]:
                title = b["text"]
                break
                
        # Clean text for Voiceover payload
        vo_text = []
        for b in blocks:
            if b["type"] in ["h1", "h2", "h3", "paragraph", "bullet"]:
                clean = re.sub(r'\*\*(.*?)\*\*', r'\1', b["text"]) # remove bold syntax for voice
                vo_text.append(clean + ".")
                
        sections.append({
            "mode": mode,
            "title": title,
            "blocks": blocks,
            "vo_payload": "  ".join(vo_text)
        })
        
    return sections

# ── Dynamic Manim Scene ───────────────────────────────────────────────────────

class DynamicScene(VoiceoverScene):
    BG        = "#0b0f19"
    ACCENT    = "#ffc107"
    WHITE_C   = "#e6edf3"
    GREY_C    = "#8b949e"
    HEADING_C = "#ffc107"
    PANEL_BG  = "#161b22"

    WRAP_WIDTH = 68

    def construct(self):
        self.set_speech_service(GTTSService())
        
        sections = parse_input("../text_creation/input.txt")
        if not sections:
            raise ValueError("Failed to parse input.txt.")
            
        for section in sections:
            self._render_section(section)

    def _bg(self):
        bg = Rectangle(
            width=config.frame_width, 
            height=config.frame_height,
            fill_color=self.BG, 
            fill_opacity=1, 
            stroke_width=0,
        )
        self.add(bg)
        return bg

    def _render_section(self, section):
        self._bg()
        mode = section.get("mode", "concept")
        vo_text = section.get("vo_payload", "")
        
        # Safe fallback if vo_text is empty
        if not vo_text.strip():
            vo_text = "Continuing."
            
        with self.voiceover(text=vo_text) as tracker:
            self._render_markdown(section["blocks"], mode)
            self.wait(2)
            
        self.play(FadeOut(*self.mobjects), run_time=0.4)

    def _format_markup(self, text):
        """Escape XML special chars then convert **bold** to Pango <b> tags."""
        # Step 1: temporarily protect **bold** spans
        parts = re.split(r'\*\*(.*?)\*\*', text)
        result = []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                # Regular text — escape XML special chars
                part = part.replace('&', '&amp;')
                part = part.replace('<', '&lt;')
                part = part.replace('>', '&gt;')
                part = part.replace('"', '&quot;')
            else:
                # Bold content — escape inner chars but keep bold tags
                inner = part.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                part = f'<b>{inner}</b>'
            result.append(part)
        return ''.join(result)

    def _render_markdown(self, blocks, mode):
        """
        Translates parsed Markdown structured blocks directly into beautiful
        native Manim components, sequenced vertically inside a VGroup.
        """
        elements = VGroup()
        mobjects_to_animate = []
        
        for b in blocks:
            btype = b["type"]
            if btype == "h1":
                txt = Text(b["text"], font_size=42, weight=BOLD, color=self.HEADING_C)
                ul = Line(txt.get_left(), txt.get_right(), color=self.ACCENT, stroke_width=2).next_to(txt, DOWN, buff=0.1)
                grp = VGroup(txt, ul)
                elements.add(grp)
                mobjects_to_animate.append((grp, "title"))
                
            elif btype == "h2":
                txt = Text(b["text"], font_size=34, weight=BOLD, color=self.HEADING_C)
                elements.add(txt)
                mobjects_to_animate.append((txt, "subtitle"))
                
            elif btype == "h3":
                txt = Text(b["text"], font_size=28, weight=BOLD, color=self.ACCENT)
                elements.add(txt)
                mobjects_to_animate.append((txt, "subtitle"))
                
            elif btype == "paragraph":
                clean_text = self._format_markup(b["text"])
                wrapped = textwrap.fill(clean_text, width=self.WRAP_WIDTH)
                txt = MarkupText(wrapped, font_size=24, color=self.WHITE_C)
                elements.add(txt)
                mobjects_to_animate.append((txt, "text"))
                
            elif btype == "bullet":
                clean_text = self._format_markup(b["text"])
                wrapped = textwrap.fill("• " + clean_text, width=self.WRAP_WIDTH - 4)
                txt = MarkupText(wrapped, font_size=24, color=self.WHITE_C)
                elements.add(txt)
                mobjects_to_animate.append((txt, "text"))
                
            elif btype == "code":
                code_obj = Code(
                    code_string=b["content"],
                    language=b["language"] if b["language"] else "python",
                    background="window",
                    add_line_numbers=False,
                    formatter_style="monokai",
                )
                
                # Scale Code to fit within reasonable horizontal width
                if code_obj.width > 12.0:
                    code_obj.scale(12.0 / code_obj.width)
                elements.add(code_obj)
                mobjects_to_animate.append((code_obj, "code"))

        if len(elements) == 0:
            return

        # Dynamically arrange everything in a top-down list
        elements.arrange(DOWN, aligned_edge=LEFT, buff=0.5)
        
        # Center title elements if desired, though Left alignment looks cleaner for documents.
        # We will keep everything Left aligned, but center the entire VGroup!
        
        # Scale to fit Screen Frame
        if elements.height > config.frame_height - 1.5:
            elements.scale((config.frame_height - 1.5) / elements.height)
        if elements.width > config.frame_width - 1.5:
            elements.scale((config.frame_width - 1.5) / elements.width)
            
        elements.move_to(ORIGIN)
        
        # Smart Animation cascade
        for obj, btype in mobjects_to_animate:
            if btype == "title":
                self.play(FadeIn(obj[0], shift=DOWN*0.1), Create(obj[1]), run_time=0.6)
            elif btype == "subtitle":
                self.play(FadeIn(obj, shift=RIGHT*0.2), run_time=0.5)
            elif btype == "text":
                self.play(Write(obj), run_time=0.5)
            elif btype == "code":
                # Background appears first
                self.play(FadeIn(obj[0]), run_time=0.4)
                # Code lines cascade
                for line in obj[1]:
                    self.play(FadeIn(line, shift=UP*0.05), run_time=0.08)
                self.wait(0.3)
