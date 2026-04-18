from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT, build_design_input_section


def build_design_change_points_template_json() -> str:
    return (
        '{\n'
        '  "change_points": [\n'
        '    {\n'
        '      "title": "__FILL__",\n'
        '      "summary": "__FILL__",\n'
        '      "constraints": ["__FILL__"],\n'
        '      "acceptance": ["__FILL__"]\n'
        '    }\n'
        '  ]\n'
        '}\n'
    )


def build_design_change_points_agent_prompt(
    *,
    title: str,
    refined_markdown: str,
    knowledge_brief_markdown: str,
    seed_change_points: list[str],
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="You are extracting normalized Design change points for coco-flow.",
        goal="Read the refined request, merge duplicates, normalize overlapping bullets, and directly edit the target JSON template file.",
        requirements=[
            "You must edit the provided JSON file directly instead of only replying in chat.",
            "Output concise, implementation-relevant change points, not repeated paraphrases.",
            "Merge near-duplicate bullets into one normalized change point.",
            "Prefer 1 to 5 change points unless the request is clearly broader.",
            "Do not invent new requirements beyond the refined request and inherited knowledge.",
            "Keep titles short and summaries concrete.",
            "When information is unclear, preserve uncertainty in summary rather than splitting into many weak points.",
            "After editing the file, reply briefly that you finished.",
        ],
        output_contract=DESIGN_OUTPUT_CONTRACT,
        sections=[
            PromptSection(
                title="Template File",
                body=f"- file: {template_path}\n- Edit this JSON file and replace every __FILL__ placeholder.",
            ),
            build_design_input_section(
                title=title,
                refined_markdown=refined_markdown,
                knowledge_brief_markdown=knowledge_brief_markdown,
            ),
            PromptSection(
                title="Seed Change Points",
                body="\n".join(f"- {item}" for item in seed_change_points) or "- no seed change points",
            ),
        ],
    )
    return render_prompt(document)
