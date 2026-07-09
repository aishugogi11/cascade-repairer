# DeepLearning.AI Voice for AI Agents and Applications Course Transcript

## Introduction

Welcome to Voice for AI Agents and Applications,
built in partnership with Vocal Bridge,
an AI Fund portfolio company and taught by CEO Ashwyn Sharma.
In this course, you'll learn how to build agents
with voice interactive user interfaces.
You add voice to your existing agents,
as well as for agents that
use voice as a function call tool.
You also apply voice evals to your agents
with detailed feedback on quality and accuracy to enhance them.
The vast majority of people on this planet
find speaking and listening much easier than writing and reading.
And as voice UIs become more reliable,
it'll open up many new applications for many people.
For example, in The Batch newsletter,
I wrote about my building a simple cat themed math quiz application
for my seven-year-old daughter.
She's enjoyed using the keyboard to play this game,
but using Vocal Bridge, I was able
to add a voice UI pretty quickly.
So I can now quiz her verbally in a
friendly way and she can respond verbally as well.
And this really changes how the experience feels.
Voice applications have historically faced a trade-off
between latency and intelligence.
One option is to use native voice-in, voice-out
or voice-to-voice real-time models,
and they're fast, but less reliable and harder to control.
The other approach is to use a pipeline that inputs audio,
uses speech-to-text, then has an LLM execute an agentic workflow,
and then finally text-to-speech to read out the response.
That's more reliable and more controllable,
but adds latency, which is a problem for real-time conversations.
In this course, you learn how to build voice applications
that are both fast and reliable.
Vocal Bridge, which you'll learn to use,
relies on a custom architecture with a fast foreground agent
for real-time conversation, as well as a background agent
for reasoning workflows, guardrails, and tools.
This gives your voice agents a best combination of both
low latency and high intelligence.
Thanks Andrew. This course teaches three integration
patterns that meet you where you are.
The first pattern is voice embedded in applications.
Think of a game or a productivity
tool where users can use voice commands,
but they can also click and interact with the UI directly.
The voice agent needs to trigger UI changes when the user speaks,
and it needs to know when the user clicks on something.
That bidirectional awareness
is what makes the experience feel natural.
The second pattern is voice for existing agents.
You've already built a Claude, GPT, or LangChain powered agent
with custom logic. You don't want to rewrite it.
Vocal Bridge sits as a thin layer in front of your agent.
It handles voice to intent conversion,
but understanding when to delegate a question to your agent
versus handling conversational pleasantries itself.
The third pattern is the voice as a tool
your LLM can call.
Imagine a recruiting agent coordinating interviews.
A candidate texts their availability
and the agent responds in text to confirm
and then also calls and coordinates the interview date
that works the best for the candidate.
Or a brainstorming agent, working with you via chat.
It says, this would be faster to talk through,
and opens a live voice session.
So the agent chooses the right modality for the moment.
We will also have Scott Johnston, former CEO of Docker,
and board member of Vocal Bridge to share with us
all the recent developments in bringing AI voice
and the landscape of voice agents and applications to production.
Many people have worked to create this course.
I'd like to thank Eli Chen and Rakesh Utekar from AI Fund,
and Aditi Dhar and Jitesh Gupta from Vocal Bridge.
From DeepLearning.AI, Brendan Brown and Esmaeil Gargari
also contributed to this course.
In the first lesson, you will learn
about the traditional voice agent stack in detail.
So you understand what's being abstracted away by Vocal Bridge.
Then you will see live demos
of all three integration patterns we discussed.
By the end of the lesson, you
will know which pattern fits your use case
and start building them in the next lessons.
This sounds great. Let's get started.

## Overview of Voice UI

In this lesson, you will learn about
the traditional voice stack with all its complexity.
Then, you will walk through three live demos
that each demonstrate a different pattern for building voice agents.
Let's dive in. This first lesson
will walk you through the voice AI landscape.
There is no notebook for this lesson.
What I want you to walk away with
is a clear mental model of three things.
One, what a production voice agent actually involves,
two, where voice belongs in your stack and three,
what we're going to build hands-on starting in lesson two.
Before we get into the architecture,
I want to spend a minute on why voice.
Why does this matter? There are four reasons
it's worth treating as a first-class modality
in the AI era. First one's the obvious one.
Voice is the most natural interface humans have.
We've been talking for hundreds of thousands of years.
Typing is just a few decades old.
So voice is the lowest friction way to express intent.
No menus, no forms, no scrolling.
Second is paralinguistics. And this one is underrated.
A voice utterance carries way more signal
than the same sentence as text.
It could be tone, pace, hesitation,
urgency, prosody, emotion.
Agents that can hear how you mean something
not just what you said. They behave really
differently from agents that just read your text.
Third is multimodality.
Voice doesn't replace your UI, it pairs with it.
You speak intent, you see structured info back.
The best voice agents are the ones
that use voice and the GUI together
each modality doing what it's best at.
Finally, the fourth one is accessibility.
Voice reaches users who cannot type
or they can't read on the screen,
can't navigate a complex GUI,
is often the most accessible interface you can ship.
And that matters.
With real-time AI, voice finally works as an interface.
and paired with your existing UI, it's
a step change in how products feel.
So, let me make that concrete.
One example that we're going to use here is booking a flight.
With a classic GUI, you go
through four phases. You open the app,
You search, you pick dates, apply filters,
and then choose from the options, and then finally pay and confirm.
Every phase has its own subtasks. Total time,
easily over two minutes and you're tapping the entire time.
Now, imagine the same task on voice with a single utterance,
book me a flight from SF to NYC next Friday morning.
The agent does the screens. You stay in the conversation.
You can confirm out loud, you'll be done in under 10 seconds.
Now the point isn't that voice replaces GUIs.
The point is voice collapses the friction between intent and outcome.
And you will see this pattern over and over
in every demo for the rest of this lesson.
So where's voice actually being used today?
And where's it going next?
This whole scene is one big picture.
What I call the voice agent universe.
And we are going to fill it one bubble at a time.
So, if you've heard about voice
AI over the last couple of years,
the context was almost certainly the contact center.
Support, IVR, Agent Assist, Call Q&A.
That's the orange cluster on the right.
Economics are clear, workflows are constrained,
the buyers exist. That's why the industry started there.
But that's a tiny slice of where voice actually belongs.
The bigger picture is the rest of this universe.
Voice as a feature of every kind of software across every industry.
Fintech, voice as the interface to your account, to your portfolio.
Or it could be in-car for the obvious reason
because you can't take your hands
off the wheel. Take Healthcare for example.
You can have use cases like clinical dictation,
patient intake, check-ins,
you name it. It could be Devtools.
Coding assistance you can actually talk to.
And obviously Accessibility for users
who can't easily use a GUI.
and productivity, meeting, scheduling, inbox agents.
And finally, education for kids who can't read yet.
Gaming, field service, the list keeps growing.
So the framing for this entire course is simple.
Voice today lives in the contact center.
But voice tomorrow lives everywhere a developer ships software.
To make it more concrete, over the rest of this course,
we will work with three surfaces
Vocal Bridge will plug into your stack.
One, voice for your application.
Using our React SDK, you can drop in our VocalBridgeProvider component
and you can voice enable any application.
The agent simplified actions and your UI can react.
Number two is voice for your agents.
Again, using our SDK and leveraging the useAIAgent hook
will give your existing LLM agent a
voice in just two lines of code.
That's lesson three. And finally, voice as a tool.
Using our CLI, "vb call" is the command that'll let your agent
place real phone calls.
Voice becomes a function your LLMs can invoke.
That's lesson four. Now, let me show you
what you would actually have to build
if you try to wire this up yourself.
And why we built Vocal Bridge to collapse all of it.
This is the production stack. 12
steps, I will walk through each one.
First block is simple Capture.
Microphone permissions, WebRTC ingest,
and the codecs, track muxing,
device hot swaps, that's just getting the audio in the door.
Next is Audio Pre-Process.
which includes noise cancellation, echo cancellation, handling silence frames.
None of this is glamorous. All of
it is what makes the agent intelligible.
You would want to add STT + Voice Accurate Detection.
You would probably want streaming speech to text,
because if you want real-time voice agents,
speech should be converted into streaming text
and you will have to leverage frameworks like Whisper, Deepgram,
voice activity detection also known as VAD
to figure out when someone's actually speaking and endpointing
for the agent to figure out when
the user is finished with their turn.
or maybe even diarization if there's more
than one speaker involved on the call.
And finally, your agent,
which will also have to be your dialogue manager.
It'll have to handle turn taking, tool routing, your RAG pipeline, memory,
the prompt, the business logic, all of it.
This is the only block that's actually about your product.
Everything else is this plumbing. Finally,
we will have text to speech coupled with sentence chunking,
selecting voices,
selecting and configuring the prosody,
synthesizing the speech in streaming or as streaming,
and choosing from a number of TTS providers.
And there are more branches that come in, right?
Specifically two branches, the Telephony Bridge.
which will require you handling the telephony stack.
So working with providers like Twilio, handling the SIP protocol,
handling DTMF, handling inbound and outbound separately.
That all of that sits above capture. And wrapping all of it,
which cuts across the different components in this architecture is authorization,
session state management, handling reconnections, failovers,
latency budgets, concurrency, observability.
And that makes up your entire stack in production.
All right. There are essentially two architectures in voice AI today.
And there's a tradeoff between them that nobody wants to make.
First one is your Cascaded setup.
It's the classic stack.
You have speech to text, then you have your LLM,
and then you finally have text to speech.
You might also need deep reasoning because
you're using your full LLM stack as is.
It is easy to debug.
Every step is text, but the latency
is going to be 1 to
3 seconds per turn, end to end,
which is not ideal for a real-time voice agent.
And speech to text strips out the
tone, the emotion, the pacing, all the paralinguistics.
You lose all of that signal
before your agent ever sees the input.
Second one is the
real-time architecture, aka voice-to-voice models.
where the input is speech and the output is also speech.
And there's just one single model.
The latency drops to, you know, 200 to 500 milliseconds.
That's the kind of latency you want.
The model hears tone, pitch, hesitation, emotion,
all the paralinguistic signals
that we lost with the cascaded stack.
But you do lose access to your LLM stack.
The brain here is generic. Wiring it
up with your RAG, with your tools,
with your domain knowledge is not straightforward.
So, you have to pick one. Either you
get Low Latency or you get deep reasoning.
Either you get naturalness or you can leverage your existing brain.
That is the tradeoff nobody wants to make.
So Vocal Bridge's answer is what we call the concierge architecture.
A real-time brain that handles the conversation.
So things like fillers, turn-taking, paralinguistics.
And it only delegates to your LLM
when it needs Deep Reasoning or
it needs to execute a specialized task
that your LLM or your agentic workflow is really good at.
So you get real-time latency and your existing LLM stack stay intact.
The implementation is really our secret sauce,
but the high-level shape is what you see on the screen.
That's the architectural picture you should walk into lesson two with.
In lesson two, we start building.

## Conclusion

In this final lesson, I will have a conversation with Scott Johnson,
former CEO of Docker and current board member of Oak Ridge.
We will discuss what it really takes to go from demos to voice in production.
Let's go.
Scott, it's great to have you here.
I'm glad we are doing this.
Most courses on voice AI walk you through how to build a working demo,
and almost none of them
prepare you for what happens after that demo gets handed to your users.
So today I wanted to spend a few minutes on the second half of that journey,
see what production actually looks like and why.
The next chapter of voice is going to be written
by a very different group of developers than the first one was.
Thanks. Ashley. I'm happy to be here.
You know, this production gap is something I've spent a career thinking about.
And while it's different technology each time, the shape of the problem is
remarkably consistent. Yeah.
And you spent more than a decade.
A Docker grew it to more than 26 million developers.
And from the outside, at least today, containers feel like a solved problem.
But they're just plumbing. Right.
But ten years ago, deploying software was genuinely hard.
What actually changed?
You know what changed wasn't that the underlying technology got invented.
Right.
Because Linux namespaces and C groups, they've been around for years.
What changed is that we made a path from I have an idea to
it's running in production
short enough that one developer could walk it on their own.
And once that path is short,
the number of people who can ship a product goes up by orders of magnitude.
And the kinds of products they ship change as well,
because suddenly the cost of trying something is really low.
Absolutely.
And that's the lens I find myself using for voice.
The underlying models have improved dramatically
over the last couple of years, but the path from
I want my app to talk to a user to a million users, I using it
reliably, is still long and still mostly traveled by specialists.
So the real question is who gets to build the next thing?
If ten teams in the world
have the patience to wire it all together, you get ten voice products.
What if a million developers can do it on a weekend?
You get an entirely different kind of category.
Totally.
So let's get concrete for the learners because this is the part.
Demo videos don't show.
And when I say production, you know I'm not talking
about a model returning the right answer in a notebook.
I am talking about it's to am
a user in Sao Paulo, is talking to your app, and your system needs to respond
in less than 600 milliseconds in that dialect, in that accent,
while calling your payments API mid-sentence.
And if any of that breaks, you need to know that within an hour,
not within a week from an angry tweet.
So latency budgets, observability, evaluation, graceful fallbacks,
the same vocabulary we'd use for any high availability system.
Exactly.
And what's interesting is that none of those problems are voice specific.
They're the same problems you would have running any distributed system.
What's Voice Pacific is that humans are spectacularly intolerant of waste failure.
If a chat agent pauses for two seconds, you just wait.
But if a voice agent pauses for two seconds, you assume a diet
and you hang up.
So I guess what I'm trying to say is the pain threshold is much lower,
which means the engineering bar has to be much higher.
Right.
I think that's the piece I think people underestimate going in.
Right.
The bar for voice and production is closer to a real time trading system.
That is for a typical web app.
You don't get to defer the hard parts.
Absolutely.
So I guess the only place anyone is seriously
deploying voice agents today is the contact center.
And there's a good reason for that.
The economics are clear, the workflows are constrained, and the buyers exist.
But that's a tiny slice of where voice actually belongs.
I would argue there are too much bigger surfaces opening up alongside it.
All right, well, give me the first one.
All right.
So I think the first is voice as a feature inside the applications
developers are already shipping.
So you know it could be a logistics dashboard for a driver
who can take their hands off the view or a coding assistant.
You can talk through a bug
with an electronic health record system a clinician can dictate into,
or maybe a learning app for a kid who can't read.
Yet in each of those, voice isn't the product.
It's a feature of the product,
which is a completely different design problem from the contact center one,
the voice layer has to live alongside the app's existing state.
Call the same tools the apps buttons already call,
and respect what the user is currently looking at on the screen.
So I strongly feel that
the stack that was built for call centers was never built for that.
And the second surface? Yeah.
And I think the second one didn't really even exist.
I guess like 2 to 3 years ago,
over the last couple of years, millions of developers have built
AI agents, agents that read code bases, agents that triage tickets, agents
that run analytics, and even agents that operate inside larger workflows.
Almost all of those agents are text only today.
And I feel that voice is the natural next interface for most of them.
And almost none of them have it yet.
What's interesting about that surface
is that the hard work on those agents is already done.
Right.
The reasoning, the tool use, the memory that's built.
What's missing is the modality.
Humans actually prefer voice, and the who built
that agent shouldn't have to rebuild it from scratch just to give it voice.
Exactly.
So the integration challenge isn't just voice
plus app anymore, it's also voice plus agent.
Your existing agent shouldn't have to become a new project
just because you want users to talk to it.
Which is why I think the next 10 million voice developers
are not going to think of themselves as voice developers at all.
They're going to be
the people who shipped a web app last year or shipped an agent this year.
Voice will just be another surface they reach for when it's the right one.
Absolutely.
So let me name a couple of things we see real teams struggle with,
because I think they're useful for learners to recognize.
The first is the integration model itself.
Most white stacks today assume the agent owns the conversation end to end.
But real applications have business logic,
authentication, databases, existing tools.
The voice agent has to be a participant in that system, not the whole thing.
Right.
And that's exactly the conversation we used to have about containers,
by the way.
You know, early on people
thought a container was supposed to be the entire VM took the industry a few years
to internalize that a container is just one piece of a larger system.
And the value comes from how cleanly composes with everything else around it.
Absolutely.
And the second thing is evaluation.
Voice has no real equivalent of a unit test yet,
because the output is a wave form and the input is a conversation.
So teams ship blindly hear about a bad call from a user
and have no systematic way
to reproduce it, regress against it, or prove the fix worked.
So building that loop the deploy the listen.
Evaluate the iterate.
That's where most of the actual production workloads.
Which is also why this should be exciting for the people taking this course.
The unsolved problems here
aren't model problems, their software engineering problems.
For the people taking this course, you've already mastered that iterative loop.
Deploy, observe, evaluate, iterate using vocal bridge.
That hands on experience is
what makes you ready to tackle production grade voice deployments.
So yeah, and that's the exact bakery I would want any learner of this course
to walk away with.
The model is no longer the bottleneck.
The bottleneck is the bullying middle the deploy the observe the evaluate
the iterate.
That's where the next generation of voice products will be one or last.
And I strongly feel
that's where the opportunity is for the developers watching this.
And historically,
every time that boring middle has gotten dramatically easier for containers,
for web hosting, for mobile, what's happened next is a wave of products
from people who are newly empowered to build them, and voices.
Next on that list, I'm going to bet on it.
Scott, thank you so much for joining us for this conversation.
This is exactly what I wanted the learners to hear.
My pleasure. Ashwin.