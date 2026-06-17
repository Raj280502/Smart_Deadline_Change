import json
import os

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

load_dotenv()


JD_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You summarize placement job descriptions for students.
Return valid JSON only with this shape:
{{
  "short_summary": "2-3 sentence role summary",
  "skills_required": ["skill 1", "skill 2"],
  "responsibilities": ["responsibility 1", "responsibility 2"],
  "eligibility_summary": "short eligibility summary",
  "important_notes": ["note 1", "note 2"]
}}

Be concise, practical, and faithful to the provided text.
"""),
    ("human", """Company: {company_name}
Role: {role}
Criteria from portal: {criteria}

Job description text:
{job_description}
""")
])


def summarize_jd(company_name: str, role: str = "", criteria: str = "",
                 job_description: str = "", api_key: str = None) -> dict:
    """
    Summarize a placement JD with Groq.

    Stack syntax:
        prompt | llm | parser
        chain.invoke({...})
    """
    if not job_description:
        return empty_summary("No JD text was available.")

    api_key = api_key or os.getenv("GROQ_API_KEY")
    if not api_key:
        return empty_summary("GROQ_API_KEY is missing, so JD was not summarized.")

    llm = ChatGroq(
        model=os.getenv("PLACEMENT_SUMMARY_MODEL", "llama-3.3-70b-versatile"),
        api_key=api_key,
        temperature=0.2,
    )
    chain = JD_SUMMARY_PROMPT | llm | StrOutputParser()

    raw = chain.invoke({
        "company_name": company_name or "Unknown company",
        "role": role or "Unknown role",
        "criteria": criteria or "Not mentioned",
        "job_description": job_description[:12000],
    })

    return parse_summary(raw)


def parse_summary(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "short_summary": text[:1000],
            "skills_required": [],
            "responsibilities": [],
            "eligibility_summary": "",
            "important_notes": ["Model returned non-JSON summary."],
        }


def empty_summary(reason: str) -> dict:
    return {
        "short_summary": reason,
        "skills_required": [],
        "responsibilities": [],
        "eligibility_summary": "",
        "important_notes": [],
    }
