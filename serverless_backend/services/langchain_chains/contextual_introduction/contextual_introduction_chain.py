import time
import json
from typing import Dict, Any
from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model_name='gpt-4')

class ContextIntroduction(BaseModel):
    needs_context: bool = Field(description="Whether the video needs contextual explaining")
    intro_transcript: str = Field(description="A very brief transcript to provide context, if needed")
    explanation: str = Field(description="Explanation for the decision and the intro transcript")

context_parser = PydanticOutputParser(pydantic_object=ContextIntroduction)

context_examples = [
    {
        "transcript": "Fisher also notes that the true test of whether a stock is currently cheap or expensive is not based on its current stock price. What determines evaluation is whether the company's fundamentals are more or less favorable than the current financial community's appraisal of that stock.",
        "short_idea": "Focus on fundamentals, not stock price fluctuations. Ignore the wrong thing, the stock price.",
        "short_idea_justification": "This idea emphasizes the key investment advice to focus on a company's fundamentals rather than its stock price. It's a clear, concise, and valuable lesson that can be visually and engagingly presented on TikTok, appealing to both novice and experienced investors.",
        "response": '{{"needs_context": true, "intro_transcript": "This is why you should NEVER focus on the stock price.", "explanation": "The video needs context because it jumps straight into discussing fundamentals vs stock price without setting up why this is important. The intro provides a dramatic hook that baits the user to continue watching, creating curiosity about why one should never focus on the stock price."}}'
    },
    {
        "transcript": "Welcome to our guide on making the perfect cup of coffee. First, start with freshly roasted beans. Grind them just before brewing for the best flavor.",
        "short_idea": "The importance of using freshly ground coffee beans",
        "short_idea_justification": "This idea highlights a crucial step in making great coffee that many people overlook. It's a simple tip that can significantly improve the taste of home-brewed coffee, making it an engaging and practical topic for TikTok.",
        "response": '{{"needs_context": false, "intro_transcript": "", "explanation": "The video doesn\'t need additional context because it already starts with a clear introduction to the topic of making the perfect cup of coffee. The existing opening sets up the content well, mentioning both fresh beans and grinding, which aligns with the short idea."}}'
    }
]

context_example_prompt = PromptTemplate(
    input_variables=["transcript", "short_idea", "short_idea_justification", "response"],
    template="""
    Transcript: {transcript}
    TikTok idea: {short_idea}
    TikTok idea justification: {short_idea_justification}
    Response: {response}
    """
)

context_prompt = FewShotPromptTemplate(
    examples=context_examples,
    example_prompt=context_example_prompt,
    prefix="""Given the transcript, TikTok idea, and justification, determine if contextual introduction is needed and provide a brief intro if necessary. Your response should be a JSON object with the following structure:
    {{
        "needs_context": boolean,
        "intro_transcript": string,
        "explanation": string
    }}
    
    Here are some examples:""",
    suffix="Now analyze:\nTranscript: {transcript}\nTikTok idea: {short_idea}\nTikTok idea justification: {short_idea_justification}\n{format_instructions}",
    input_variables=["transcript", "short_idea", "short_idea_justification"],
    partial_variables={"format_instructions": context_parser.get_format_instructions()},
)

context_chain = (context_prompt | model | context_parser).with_config(
    {"run_name": "Generate Context Introduction", "tags": ["context-introduction"]}
)

def retry_with_exponential_backoff(
    func,
    max_retries: int = 5,
    initial_delay: float = 1,
    exponential_base: float = 2,
    errors: tuple = (Exception,),
) -> Any:
    """
    Retry a function with exponential backoff.
    """
    def wrapper(*args, **kwargs):
        delay = initial_delay
        for i in range(max_retries):
            try:
                return func(*args, **kwargs)
            except errors as e:
                if i == max_retries - 1:
                    raise
                print(f"Attempt {i+1} failed with error: {str(e)}. Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= exponential_base
    return wrapper

@retry_with_exponential_backoff
def generate_context_introduction(transcript: str, short_idea: str, short_idea_justification: str) -> Dict[str, Any]:
    result = context_chain.invoke({
        "transcript": transcript,
        "short_idea": short_idea,
        "short_idea_justification": short_idea_justification
    })
    return result.dict()



if __name__=="__main__":
    # Example usage
    transcript = "Fisher also notes that the true test of whether a stock is currently cheap or expensive is not based on its current stock price. What determines evaluation is whether the company's fundamentals are more or less favorable than the current financial community's appraisal of that stock."
    short_idea = "Focus on fundamentals, not stock price fluctuations. Ignore the wrong thing, the stock price."
    short_idea_justification = "This idea emphasizes the key investment advice to focus on a company's fundamentals rather than its stock price. It's a clear, concise, and valuable lesson that can be visually and engagingly presented on TikTok, appealing to both novice and experienced investors."

    try:
        result = generate_context_introduction(transcript, short_idea, short_idea_justification)
        print(result)
    except Exception as e:
        print(f"Failed to generate context introduction after multiple retries: {str(e)}")