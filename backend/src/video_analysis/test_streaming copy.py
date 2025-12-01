import time
import threading
import queue
from datetime import datetime
from google import genai
from PIL import Image
import io
import base64
import numpy as np 
from elevenlabs import ElevenLabs
from moviepy import VideoFileClip
from moviepy import ImageSequenceClip, AudioFileClip
import os
import cv2

import queue  # <--- AJOUTER IMPORT
import json   # <--- AJOUTER IMPORT

# Configure Gemini
client = genai.Client(api_key="AIzaSyAiyGS8_ssWYKmgAMlknI6PtRdYi1GlKac")
ELEVENLABS_API_KEY="sk_7f3ece695ae82281ac98e928e46799cbb1aa5303377644d0"

class WebcamGeminiProcessor:
    def __init__(self,path_video):
        self.cap = cv2.VideoCapture(path_video)

        if not self.cap.isOpened():
            raise ValueError(f"Impossible d'ouvrir la vidéo: {path_video}")

        self.frame_buffer = []  # Store last 20 frames
        self.frame_total = []
        self.running = True
        self.send_interval = 20  # seconds
        self.send = False
        self.frame_process = 0
        self.lenght = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        ret, frame = self.cap.read()
        # self.height, self.width, self.layers = frame.shape
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        print(f"Reported FPS: {fps}")
        # cut_thread = threading.Thread(target=self.cut_video_by_frames_moviepy, daemon=True)
        # cut_thread.start()

        self.event_queue = queue.Queue() 
        self.chunk_index = 0

        self.processing_threads = []
        
    def capture_frames(self):
        """Continuously capture frames from webcam"""
        frame_count = 0 
        fps = 30
        while self.running:
            ret, frame = self.cap.read()

            if not ret or frame is None:
                print("Fin de la vidéo source atteinte.")
                break # On sort juste de la boucle, ON NE TOUCHE PAS à self.running

            if frame_count % 6 == 0 :
                _, encoded = cv2.imencode('.jpg', frame)
                self.frame_total.append(encoded)
            
            if not ret:
                print("Failed to capture frame")
                break
            # Show the frame
            cv2.imshow('Webcam Feed', frame)

            if frame_count % fps == 0 :

                # Add timestamp to frame display
                timestamp = datetime.now().strftime("%H:%M:%S")
                cv2.putText(frame, timestamp, (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                pil_image = Image.fromarray(frame)
                self.frame_buffer.append(pil_image)
                
                # print(f"framecount : {frame_count}, buffer lenght {len(self.frame_buffer)}")
                # Check if it's time to send to Gemini
                if len(self.frame_buffer) > self.send_interval:
                    gemini_thread = threading.Thread(target=self.process_with_gemini,args=(self.frame_buffer,self.frame_total,), daemon=True)
                    gemini_thread.start()
                    self.processing_threads.append(gemini_thread)
                    self.frame_buffer = []
                    self.frame_total = []
            
            frame_count += 1
            # Check for quit command
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.running = False
                break
            
            # Maintain 1 fps
            # time.sleep(1)
    
    def cut_video_by_frames_moviepy(self,):
        # input_path = "videos/33goals.mp4"
        # clip = VideoFileClip(input_path)
        # start_time = 0 
        # while self.lenght > start_time + 20 : 
        #     print("new_clip") 
        #     # Calculate start and end times based on frames and FPS
        #     end_time = start_time + 20

        #     # Cut the clip
        #     subclip = clip.subclipped(start_time, end_time)
            
        #     # Write the output file
        #     output_path = f"clip_frame_{start_time}.mp4"
        #     subclip.write_videofile(output_path, codec="libx264")

        #     start_time += 20
        #     # time.sleep(10)
        return 0
    
    def reconstruct_from_encoded_images(self,encoded_images, output_path, fps=5, codec='mp4v'):
        """
        Reconstruct an MP4 video from a list of CV2-encoded JPG images (numpy arrays).
        
        Args:
            encoded_images: List of encoded image data (result of cv2.imencode)
            output_path: Path for the output MP4 file
            fps: Frames per second for the output video (default: 30)
            codec: Video codec to use (default: 'mp4v')
        """
        # print("start reconstruct")
        # print(encoded_images)
        if not encoded_images:
            raise ValueError("Encoded images list is empty")
        
        # Decode the first image to get dimensions
        first_img = cv2.imdecode(encoded_images[0], cv2.IMREAD_COLOR)
        if first_img is None:
            raise ValueError("Could not decode first image")
        
        height, width, _ = first_img.shape
        
        # Define the codec and create VideoWriter
        fourcc = cv2.VideoWriter_fourcc(*codec)
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        if not out.isOpened():
            raise RuntimeError("Failed to open video writer")
        
        print(f"Creating video: {output_path}")
        print(f"Dimensions: {width}x{height}, FPS: {fps}")
        print(f"Processing {len(encoded_images)} encoded images...")
        
        # Decode and write each image to video
        for i, encoded_img in enumerate(encoded_images):
            img = cv2.imdecode(encoded_img, cv2.IMREAD_COLOR)
            
            if img is None:
                print(f"Warning: Could not decode image {i}, skipping...")
                continue
            
            # Resize if dimensions don't match
            if img.shape[:2] != (height, width):
                img = cv2.resize(img, (width, height))
            
            out.write(img)
            
            # if (i + 1) % 10 == 0:
                # print(f"Processed {i + 1}/{len(encoded_images)} images")
        
        out.release()
        print(f"Video saved successfully to {output_path}")

    def add_audio_to_video(self,video_path, audio_path, output_path, audio_start=0, video_start=0):
        """
        Add audio to an existing video file.
        
        Args:
            video_path: Path to the input video file
            audio_path: Path to the audio file (mp3, wav, etc.)
            output_path: Path for the output video with audio
            audio_start: Start time in audio file (seconds, default: 0)
            video_start: Start time in video to place audio (seconds, default: 0)
        """
        print(f"Adding audio to video...")
        print(f"Video: {video_path}")
        print(f"Audio: {audio_path}")
        
        try:
            # Load video and audio
            video = VideoFileClip(video_path)
            audio = AudioFileClip(audio_path)
            
            # Trim audio if needed
            if audio_start > 0:
                audio = audio.subclipped(audio_start)
            
            # Adjust audio duration to match video if needed
            if audio.duration > video.duration:
                print(f"Trimming audio from {audio.duration:.2f}s to {video.duration:.2f}s")
                audio = audio.subclipped(0, video.duration)
            elif audio.duration < video.duration:
                print(f"Warning: Audio ({audio.duration:.2f}s) is shorter than video ({video.duration:.2f}s)")
            
            # Set audio to video
            if video_start > 0:
                # Create a delayed audio that starts at video_start
                audio = audio.set_start(video_start)
            
            final_video = video.with_audio(audio)
            
            # Write the result
            final_video.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=f'{audio_path.split(".")[0]}.m4a',
                remove_temp=True
            )
            
            # Clean up
            video.close()
            audio.close()
            final_video.close()
            
            print(f"Video with audio saved to {output_path}")
            
        except Exception as e:
            print(f"Error adding audio: {e}")
            raise

    
    def save_wav_and_images(wav_path, image_list, output_path, fps=5):
        """
        Combine a WAV audio file with a list of images into a video file.
        
        Args:
            wav_path: Path to the .wav audio file
            image_list: List of images (PIL Images, numpy arrays, or file paths)
            output_path: Path to save the output video (e.g., 'output.mp4')
            fps: Frames per second (default: 30)
        """
        print("save_wav")
        print(image_list)
        # Convert images to numpy arrays if needed
        image_arrays = []
        for img in image_list:
            if isinstance(img, str):
                # If it's a file path
                img = Image.open(img)
            if isinstance(img, Image.Image):
                # Convert PIL Image to numpy array
                img = np.array(img)
            
            # Ensure image is in the correct format (RGB)
            if img.ndim == 2:  # Grayscale
                img = np.stack([img] * 3, axis=-1)
            elif img.shape[2] == 4:  # RGBA
                img = img[:, :, :3]
            
            image_arrays.append(img)
        
        print("audio")
        # Load audio
        audio_clip = AudioFileClip(wav_path)
        print("video")
        # Create video clip from images
        video_clip = ImageSequenceClip(image_arrays, fps=fps)
        
        # Adjust video duration to match audio
        video_clip = video_clip.set_duration(audio_clip.duration)
        
        # If video is shorter than audio, loop the images
        if video_clip.duration < audio_clip.duration:
            # Loop the video to match audio duration
            video_clip = video_clip.loop(duration=audio_clip.duration)
        
        # Attach audio to video
        final_clip = video_clip.set_audio(audio_clip)
        print("writting")
        # Write the final video file
        final_clip.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            fps=fps,
            preset='medium'  # Options: ultrafast, fast, medium, slow, veryslow
        )
        
        # Clean up
        video_clip.close()
        audio_clip.close()
        final_clip.close()
        
        print(f"Video saved successfully to {output_path}")




    def generate_tts_audio(self,text: str, voice_id: str,path: str) -> str:
            print("TTS starting")
            """
            Generate TTS audio using ElevenLabs API and return as base64 string.

            Args:
                text: The text to convert to speech
                voice_id: The ElevenLabs voice ID to use

            Returns:
                Base64 encoded audio data
            """
        
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

            # Generate audio using ElevenLabs API
            audio_generator = client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_multilingual_v2"
            )

            # Collect all audio chunks
            audio_bytes = b''
            for chunk in audio_generator:
                audio_bytes += chunk
            with open(path, mode='bx') as f:
                f.write(audio_bytes)

            # Convert to base64
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

            return audio_base64

    def process_with_gemini(self,frame_buffer,frame_total):
        """Process frames with Gemini in a separate thread"""
        start = datetime.now().strftime('%H:%M:%S')
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Sending frame to Gemini...")                    
        # Send to Gemini
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[frame_buffer,'Those are a list of image from the same video at 1 fps, describe the video. Be very counsice inshort phrases'],
            )
            # print(f"""Start = : [{start}] 
                  
            #       Gemini response: {response.text}

            #       End = [{datetime.now().strftime('%H:%M:%S')}]""")
            
            self.frame_process += 20
            number = self.frame_process
            # print(self.frame_process)

            # self.save_wav_and_images(f'myfile{self.frame_process}.wav',frame_total,f'output{self.frame_process}.mp4')

            # Reconstruction et Audio (Code existant, juste vérifier les chemins)
            filename_video = f'video{number}.mp4'
            filename_audio = f'sound{number}.wav'
            filename_final = f'completed{number}.mp4'
            
            output_video_path = os.path.join(self.starting_path, filename_video)
            output_audio_path = os.path.join(self.starting_path, filename_audio)
            final_output_path = os.path.join(self.starting_path, filename_final)
            
            
            voice_id = "nrD2uNU2IUYtedZegcGx"
            self.generate_tts_audio(response.text, voice_id, output_audio_path)
            self.reconstruct_from_encoded_images(frame_total, output_video_path)
            time.sleep(2) # Petit buffer
            self.add_audio_to_video(output_video_path, output_audio_path, final_output_path)

            # On met à jour la playlist
            self.update_playlist(self.starting_path, filename_final)
            # -----------------

            # MODIFICATION ICI : On pointe vers l'endpoint FastAPI créé ci-dessus
            folder_name = os.path.basename(self.starting_path)
            # Note: Si votre router a un préfixe (ex: /api), ajoutez-le ici (ex: /api/outputs/...)
            relative_url = f"/outputs/{folder_name}/{filename_final}"

            # relative_url = f"/static/{os.path.basename(self.starting_path)}/{filename_final}"
            
            event_data = {
                "type": "chunk_ready",
                "index": self.chunk_index,
                "url": relative_url,
                "start_time": self.chunk_index * 20, # Approximation
                "end_time": (self.chunk_index + 1) * 20,
                "progress": min((self.chunk_index + 1) * 10, 100) # Fake progress
            }
            
            self.event_queue.put(event_data)
            self.chunk_index += 1
            
            # from moviepy.editor import VideoFileClip, AudioFileClip

            # # Load the video clip (without audio)
            # video_clip = VideoFileClip("output_video_without_audio.mp4")

            # # Load the audio clip
            # audio_clip = AudioFileClip("original_audio.mp3")

            # # Set the audio of the video clip
            # final_clip = video_clip.set_audio(audio_clip)

            # # Write the final video with audio
            # final_clip.write_videofile("final_video_with_audio.mp4", codec="libx264", audio_codec="aac")

            # # Close the clips
            # video_clip.close()
            # audio_clip.close()
            

        except Exception as e:
            print(f"Gemini API error: {e}")
            self.event_queue.put({"type": "error", "message": str(e)})
               
    
    def run(self):
        outputs_path = "outputs"
        try:
            os.mkdir(outputs_path)
            print(f"Directory '{outputs_path}' created successfully.")
        except FileExistsError:
            print(f"Directory '{outputs_path}' already exists.")
        except OSError as e:
            print(f"Error creating directory: {e}")

        new_directory_path = f"{outputs_path}/version_{datetime.now().strftime('%H%M%S')}"
        try:
            os.mkdir(new_directory_path)
            print(f"Directory '{new_directory_path}' created successfully.")
        except FileExistsError:
            print(f"Directory '{new_directory_path}' already exists.")
        except OSError as e:
            print(f"Error creating directory: {e}")
        """Start the webcam capture and Gemini processing"""
        self.starting_path = new_directory_path
        self.event_queue.put({"type": "status", "message": "Starting analysis...", "progress": 0})

        # Démarrage de la capture
        capture_thread = threading.Thread(target=self.capture_frames, daemon=True)
        capture_thread.start()
        
        print("Traitement démarré...")
        
        # 1. On attend que la lecture de la vidéo soit finie
        capture_thread.join()
        print("Lecture vidéo terminée. Attente de la fin des traitements Gemini/TTS...")

        # 2. On attend que tous les threads de traitement (Gemini -> TTS -> Video) aient fini
        for t in self.processing_threads:
            if t.is_alive():
                t.join()
        
        print("Tous les chunks vidéo ont été générés.")

        # 3. (Optionnel) Votre demande spécifique : attendre 20 secondes de plus
        # Cela permet au Frontend d'avoir le temps de télécharger les derniers morceaux
        print("Attente de sécurité de 20 secondes avant fermeture du flux...")
        time.sleep(20)

        # 4. MAINTENANT, on peut fermer proprement
        self.running = False
        
        # On ferme la playlist HLS si vous utilisez la méthode HLS
        # self.update_playlist(self.starting_path, "", is_end=True) 

        self.cap.release()
        print("Shutdown complete.")

    def stream_generator(self):
        """Générateur pour FastAPI StreamingResponse"""
        # Démarrer le process
        threading.Thread(target=self.run, daemon=True).start()
        
        while True:
            try:
                # On attend un event dans la file (timeout pour ne pas bloquer si fini)
                data = self.event_queue.get(timeout=1)
                
                # Format SSE (Server-Sent Events) : "data: {...}\n\n"
                yield f"data: {json.dumps(data)}\n\n"
                
                if data.get("type") == "complete" or data.get("type") == "error":
                    break
            except queue.Empty:
                # Si la capture est finie et la queue vide, on arrête
                if not self.running and self.event_queue.empty():
                    yield f"data: {json.dumps({'type': 'complete'})}\n\n"
                    break
                # Sinon on continue d'attendre (keep-alive)
                yield ": keep-alive\n\n"


    def update_playlist(self, folder_path, filename, duration=20.0, is_end=False):
            """Met à jour le fichier stream.m3u8 pour inclure le nouveau chunk."""
            playlist_path = os.path.join(folder_path, "stream.m3u8")
            
            # Si c'est le premier chunk, on crée l'en-tête
            if not os.path.exists(playlist_path):
                with open(playlist_path, 'w') as f:
                    f.write("#EXTM3U\n")
                    f.write("#EXT-X-VERSION:3\n")
                    f.write(f"#EXT-X-TARGETDURATION:{int(duration) + 2}\n") # Marge de sécurité
                    f.write("#EXT-X-MEDIA-SEQUENCE:0\n")
                    # On permet au cache de ne pas stocker la playlist pour qu'elle se rafraichisse
                    f.write("#EXT-X-PLAYLIST-TYPE:EVENT\n") 
            
            # On ajoute le chunk à la fin (mais avant le marqueur de fin si on rouvrait le fichier)
            with open(playlist_path, 'a') as f:
                if not is_end:
                    f.write(f"#EXTINF:{duration},\n")
                    f.write(f"{filename}\n")
                else:
                    f.write("#EXT-X-ENDLIST\n")

if __name__ == "__main__":
    processor = WebcamGeminiProcessor("videos/33goals.mp4")
    processor.run()