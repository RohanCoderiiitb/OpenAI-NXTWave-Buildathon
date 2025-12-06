#Generating the recipe ideas based on the user's voice input 
#in which he/she will tell the AI the ingredients available

#Importing necessary libraries
from openai import OpenAI

class RecipeGenerator:
    """
    This class generates recipe ideas based on voice input of ingredients by the user in
    any language, processes it and gives the user options of different recipes that can be 
    prepared from those ingredients. After the user picks an option, it gives the recipe and
    how the final dish may look like.
    """
    def __init__(self, audio_file_path):
        self.audio_file_path = audio_file_path

    