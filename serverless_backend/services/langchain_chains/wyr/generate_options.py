from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate, FewShotPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI
from typing import Optional

model = ChatOpenAI(model_name='gpt-4o')


class OptionOutput(BaseModel):
    transcript: str = Field(description="A brief transcript to introduce the options")
    option1: str = Field(description="First option for the video")
    option2: str = Field(description="Second option for the video")
    option1_percentage: int = Field(description="Percentage of people estimated to choose option 1")


option_parser = PydanticOutputParser(pydantic_object=OptionOutput)

examples = [
    {
        "theme": "Make Your Team",
        "explanation": "Focuses on team composition choices for a basketball team",
        "specific_instructions": "Focus on point guards",
        "transcript": "Pick a point guard",
        "option1": "Steph Curry",
        "option2": "Kyrie Irving",
        "option1_percentage": 58
    },
    {
        "theme": "Unplug This Device",
        "explanation": "Explores choices about removing specific technologies from daily life",
        "specific_instructions": "Compare two popular social media platforms",
        "transcript": "Which app disappears?",
        "option1": "Instagram",
        "option2": "TikTok",
        "option1_percentage": 62
    },
    {
        "theme": "Flavor Fusion Faceoff",
        "explanation": "Presents choices between unique and unexpected flavor combinations",
        "specific_instructions": "Use one savory and one sweet ingredient in each option",
        "transcript": "Taste this combo",
        "option1": "Bacon cheesecake",
        "option2": "Chili chocolate",
        "option1_percentage": 45
    }
]

example_template = """
Theme: {theme}
Explanation: {explanation}
Specific Instructions: {specific_instructions}
Transcript: "{transcript}"
Option 1: "{option1}"
Option 2: "{option2}"
Percentage choosing Option 1: {option1_percentage}%
"""

few_shot_prompt = FewShotPromptTemplate(
    examples=examples,
    example_prompt=PromptTemplate(template=example_template,
                                  input_variables=["theme", "explanation", "specific_instructions", "transcript",
                                                   "option1", "option2", "option1_percentage"]),
    prefix="Generate a brief transcript, two concise options, and estimate the percentage of people who would choose Option 1 for a TikTok 'Would You Rather' style video. The transcript should be a few words, each option should be brief (1-3 words if possible), and the percentage should be a whole number. Here are some examples:",
    suffix="Now, generate options for the following:\nTheme: {theme}\nExplanation: {explanation}\nSpecific Instructions: {specific_instructions}\n{format_instructions}",
    input_variables=["theme", "explanation", "specific_instructions"],
    partial_variables={"format_instructions": option_parser.get_format_instructions()}
)

option_chain = (few_shot_prompt | model | option_parser).with_config(
    {"run_name": "Generate Video Options with Percentage", "tags": ["option-generation"]}
)


def generate_options(theme: str, explanation: str, specific_instructions: Optional[str] = "") -> OptionOutput:
    """
    Generate a transcript, two options, and an estimated percentage for a TikTok video based on a given theme and explanation.

    Args:
        theme (str): The broad theme or category for the video.
        explanation (str): An explanation of the theme to provide context.
        specific_instructions (str, optional): Any specific instructions for option generation.

    Returns:
        OptionOutput: An object containing the transcript, two options, and the estimated percentage for option 1.
    """
    result = option_chain.invoke({
        "theme": theme,
        "explanation": explanation,
        "specific_instructions": specific_instructions
    })
    return result


if __name__ == "__main__":
    # Example usage
    test_cases = [
        {
            "theme": "Garden Dilemmas",
            "explanation": "Presents choices between different plants or gardening strategies",
            "specific_instructions": "Focus on pest control methods"
        },
        {
            "theme": "Astronomical Choices",
            "explanation": "Offers choices related to space exploration and celestial bodies",
            "specific_instructions": "Compare two planets to visit"
        },
        {
            "theme": "Fashion Face-Off",
            "explanation": "Presents choices between different style elements or fashion eras",
            "specific_instructions": "Compare two iconic fashion decades"
        }
    ]

    for case in test_cases:
        try:
            result = generate_options(case["theme"], case["explanation"], case["specific_instructions"])
            print(f"\nTheme: {case['theme']}")
            print(f"Transcript: \"{result.transcript}\"")
            print(f"Option 1: \"{result.option1}\"")
            print(f"Option 2: \"{result.option2}\"")
            print(f"Percentage choosing Option 1: {result.option1_percentage}%")
        except Exception as e:
            print(f"Failed to generate options for '{case['theme']}': {str(e)}")