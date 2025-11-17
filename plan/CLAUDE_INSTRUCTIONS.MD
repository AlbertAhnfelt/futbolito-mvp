You are a master LLM- and API-programmer. I need you to help me rebuild the pipeline for video analysis, in order to make it faster and better. It is important to keep all the processes simple and efficient. If you have any questions, answer me. Also update your Claude.md file to know how long in the process you have come to solving this.

How it is now:
I am using Gemini API to analyse a video input. We have a graph LLM in place, which splits the video into snippets and catagorises them according to how intense they are. Then, it calls Gemini on the individual snippets, to create a description of what is going on and to simulate commentary.

How I want to change it:

I want to remove the graph LLM entirely. The new pipeline should instead consist of two separate processes, called "analysis" and "commentary"

The analysis-process call Gemini API to analyse 60 second intervals of the video seperatly in order to find events. So if a video is 2 min 13 seconds long, it should analyse it this way:
0-60sec
60sec-120sec
120sec-133sec

The Gemini should analyse these 60sec-snippets with metadata-cutting, which is mentioned how to do it in the file docs/gemini_api_docs.md.

Then, for each segment, the events of the match should be added into a large .json file called "events.json". This .json file contains a chronical list of all things that has happened in the match, and has this information:
- time in HH:MM:SS
- a precise description of what exactly everything that happened with football language
- a true/false (1/0) parameter in integer, if it's a replay or not. 1 is replay, 0 is not.
- a integer rating 1 to 10 in how intense the event is

In a file called plan/system_prompt.md, i have further instructions on how to prompt the event detector specifically.

After the first 60 seconds of events are added to events.json, a separate process "commentary" should start. I want this processes to run simulatenously as the "analyis"-part, according to the "streaming"-instructions mentioned in the gemini_api_docs.md. This commentary-process takes the input of events.json, and outputs in a new file: "commentary.json", which consist of the actual commentary output. commentary.json has these parameters:
- start_time in HH:MM:SS
- end_time in HH:MM:SS
- commentary, which consist of a simulated football-commentary/description based on the events between start_time and end_time.

These entries in commentaries should be 5 to 30 seconds long, and have a 1-4 second long gap between the last end_time and the following start_time. It is also important that the commentary output is not longer in the time it takes to say it. So if the duration of the entry is 10 seconds, it should maximally take 10 seconds to say it, which is rougly 25 words (2.5words/second). Following is an example of what is allowed and what is not allowed:

OK:

start_time: 00:00:00
end_time: 00:00:06
commentary "example 1.1"

start_time: 00:00:07
end_time: 00:00:27
commentary "example 1.2"


NOT OK:

start_time: 00:00:00
end_time: 00:00:04
commentary "example 2.1"

start_time: 00:00:04
end_time: 00:00:35
commentary "example 2.2"

(this one had a too short entry, a too long entry, and didn't have enough space between them)

These commentary snippets are lastly to be processed in a similar way to the current implementation via elevenlabs, and then re-added to the video, also in the way that it works now. The audio should be added at the exact time specified by start_time. So if "start_time" is 00:00:13, the audio should be added at 00:00:13.

Go ahead and plan and build.