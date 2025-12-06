import sounddevice as sd
import soundfile as sf
import numpy as np

def test_mic():
    print("Scanning audio devices...")
    print(sd.query_devices())
    
    print("\n" + "="*40)
    device_id = input("Enter the DEVICE ID of your microphone (the number on the left): ")
    device_id = int(device_id)
    
    fs = 44100
    duration = 5
    
    print(f"\nRecording for {duration} seconds on Device {device_id}...")
    print("(Speak something now!)")
    
    try:
        # We force 'blocking=True' so the code MUST wait for recording to finish
        recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, device=device_id, blocking=True)
        print("Recording finished!")
        
        filename = "test_mic.wav"
        sf.write(filename, recording, fs)
        print(f"Saved to {filename}. Play this file to check if it worked.")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        print("Try a different device ID.")

if __name__ == "__main__":
    test_mic()