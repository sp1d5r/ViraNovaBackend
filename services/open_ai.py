import os

from openai import OpenAI
import json
import time
from dotenv import load_dotenv

load_dotenv()


class OpenAIService():
    def __init__(self):
        self.key = os.getenv("OPENAI_API_KEY")  # Replace this with the users API key
        # print(self.key)
        self.client = OpenAI(
            api_key=self.key,
        )

    def get_embeddings(self, transcripts, update_progress, step_size=3, step=3):
        total_transcripts = len(transcripts)
        embeddings_recorded = []
        for start in range(0, total_transcripts, step):
            try:
                update_progress(start / total_transcripts * 100)
                end = start + step_size
                end = min(end, total_transcripts)

                transcript_chunk = [transcripts[i]['transcript'] for i in range(start, end)]
                transcript_chunk_content = " ".join(transcript_chunk)

                # Simulate getting the embeddings for the chunk (replace with actual API calls)
                response = self.client.embeddings.create(
                    input=transcript_chunk_content,
                    model="text-embedding-3-small"
                )
                embedding_response = response.json()
                embedding_json = json.loads(embedding_response)
                text_embedding = embedding_json['data'][0]['embedding']

                # Store the embeddings
                embeddings_recorded.extend([text_embedding] * step)
                time.sleep(3)

            except Exception as e:
                print(f"An unexpected error occurred: {str(e)}")
                # Handle other exceptions appropriately

        # Truncate the embeddings list to match the DataFrame length if it's longer
        embeddings_recorded = embeddings_recorded[:total_transcripts]
        return embeddings_recorded

    def extract_moderation_metrics(self, segment_text):
        # Assuming 'response' is a dictionary like the provided JSON
        response = self.client.moderations.create(input=segment_text)
        results = response.results[0]
        print(results)
        metrics = {
            "flagged": results.flagged,
            "harassment": results.categories.harassment,
            "harassment_threatening": results.categories.harassment_threatening,
            "hate": results.categories.hate,
            "hate_threatening": results.categories.hate_threatening,
            "self_harm": results.categories.self_harm,
            "self_harm_intent": results.categories.self_harm_intent,
            "sexual": results.categories.sexual,
            "sexual_minors": results.categories.sexual_minors,
        }

        print(metrics)
        return metrics

    def get_segment_summary(self, segment_index, segment_text, previous_segment):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "summarise_segment",
                    "description": "Summarise the segment given, update the previous segment summary to now include the information captured information from the new segment, and finally give a catchy fun name to the new segment.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "segment_summary": {
                                "type": "string",
                                "description": "The summary of the current segment provided",
                            },
                            "segment_title": {
                                "type": "string",
                                "description": "The title to the new segment."
                            },
                            "new_combined_summary": {
                                "type": "string",
                                "description": "The new continuous summary of all the previous segments to now include the new most recent segment"
                            },
                        }
                    },
                }
            }
        ]


        prompt = (
                  f"Segment Index: {segment_index}, \n"
                  f"Previous Segments Summary: {previous_segment} \n"
                  f"Segment Transcript: {segment_text}, \n"
                  f"Your Response:")
        completion = self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system",
                 "content": "You are a topical segment describer. Your goal is to take in a video transcript, segment index, and a subset of the diarized transcript, and call the function summarise_segment. For the parameters, provide a summary of the segment in the parameter segment_summary try to include information that stands out in the example segment. For the segment_title, give a fun exciting name for the segment. For new_combined_summary parameter investigate the Previous Segments Summary and update it to include some information about what we've learned from the new segment, this summary should be a lot more brief and will be used to understand what's occured in the video so far.."},
                {"role": "user", "content": prompt}
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "summarise_segment"}}
        )

        response = json.loads(completion.choices[0].message.tool_calls[0].function.arguments)
        return response
