from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate, FewShotPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI
from typing import List, Optional

model = ChatOpenAI(model_name='gpt-4o')

class ThemeOutput(BaseModel):
    themes: List[str] = Field(description="List of generated broad themes")
    explanations: List[str] = Field(description="Explanations for each generated theme")

theme_parser = PydanticOutputParser(pydantic_object=ThemeOutput)


examples = [
    {
        "niche": "Basketball",
        "prompt": "Focus on player comparisons",
        "themes": [
            "Make Your Dream Team",
            "Who's the GOAT?",
            "Era vs Era"
        ],
        "explanations": [
            "Compares players for ideal team composition, e.g., 'Magic Johnson or Steph Curry for point guard?'",
            "Debates the greatest players of all time, e.g., 'Michael Jordan or LeBron James?'",
            "Pits players from different eras against each other, e.g., '90s Bulls or 2010s Warriors?'"
        ]
    },
    {
        "niche": "Technology",
        "prompt": "Consider ethical dilemmas",
        "themes": [
            "AI Takeover",
            "Privacy vs Convenience",
            "Digital Detox Dilemmas"
        ],
        "explanations": [
            "Explores choices about AI integration, e.g., 'AI-driven healthcare or human doctors only?'",
            "Presents trade-offs between privacy and tech benefits, e.g., 'Total online privacy or personalized services?'",
            "Offers choices about disconnecting from technology, e.g., 'No smartphone for a year or no social media forever?'"
        ]
    }
]


example_template = """
Niche: {niche}
Prompt: {prompt}
Themes:
{themes}
Explanations:
{explanations}
"""

few_shot_prompt = FewShotPromptTemplate(
    examples=examples,
    example_prompt=PromptTemplate(template=example_template,
                                  input_variables=["niche", "prompt", "themes", "explanations"]),
    prefix="Generate broad themes for 'Would You Rather' style TikTok videos based on a given niche. Each theme should be a category that can encompass multiple specific video ideas. Consider any additional instructions provided. Here are some examples:",
    suffix="Now, given the niche: {niche}, the optional prompt: {prompt}, and the number of ideas to generate: {number_of_ideas}, generate {number_of_ideas} unique and engaging broad themes specific to this niche.\n{format_instructions}",
    input_variables=["niche", "prompt", "number_of_ideas"],
    partial_variables={"format_instructions": theme_parser.get_format_instructions()}
)

theme_chain = (few_shot_prompt | model | theme_parser).with_config(
    {"run_name": "Generate Broad Themes", "tags": ["theme-generation"]}
)

def generate_themes(niche: str, prompt: Optional[str] = None, number_of_ideas: int = 3) -> ThemeOutput:
    """
    Generate broad themes based on a given niche, optional prompt, and number of ideas.

    Args:
        niche (str): The niche or topic for theme generation.
        prompt (Optional[str]): Additional instructions or context for theme generation.
        number_of_ideas (int): The number of themes to generate. Defaults to 3.

    Returns:
        ThemeOutput: An object containing lists of themes and their explanations.
    """
    result = theme_chain.invoke({
        "niche": niche,
        "prompt": prompt or "",
        "number_of_ideas": number_of_ideas
    })
    return result

if __name__ == "__main__":
    test_cases = [
        {"niche": "Astronomy", "prompt": "Focus on space exploration dilemmas", "number_of_ideas": 2},
        {"niche": "Fashion", "prompt": "Consider sustainability vs style trade-offs", "number_of_ideas": 4},
        {"niche": "Urban Planning", "prompt": None, "number_of_ideas": 3}
    ]

    for case in test_cases:
        try:
            result = generate_themes(case["niche"], case["prompt"], case["number_of_ideas"])
            print(f"\nGenerated Themes for '{case['niche']}' (Prompt: {case['prompt'] or 'None'}, Number of Ideas: {case['number_of_ideas']}):")
            for theme, explanation in zip(result.themes, result.explanations):
                print(f"- {theme}")
                print(f"  Explanation: {explanation}\n")
        except Exception as e:
            print(f"Failed to generate themes for '{case['niche']}': {str(e)}")
