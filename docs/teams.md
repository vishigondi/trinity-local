---
class: live
---

# Trinity for Teams — vendor-neutral agent memory

> Private beta. The single-user Trinity Local is MIT and free forever; this
> document describes the team offering for organizations that want the
> same architecture inside their environment.

Trinity for Teams brings the same architecture — local routing across Claude,
GPT, and Gemini, with consolidated patterns staying in your environment — to
organizations that want the productivity gains of agent memory without
committing to any one lab's runtime.

## Two enterprise concerns Trinity answers directly

- **Data residency / compliance.** Claude Managed Agents runs memory +
  orchestration on Anthropic's hosted runtime. For regulated industries
  this is a non-starter — you have to prove residency. Trinity keeps
  everything in `~/.trinity/` on infrastructure you own. Configure it
  inside your VPC and the council outputs never cross your network
  boundary.

- **Stack composability.** Trinity doesn't replace LangGraph, CrewAI,
  Pinecone, DeepEval, or your existing eval pipeline. It sits *above* the
  model choice — your existing stack handles within-Claude state and
  within-Claude eval; Trinity routes the higher-level decision of *which
  lab to ask for which kind of question.* The article framing is binary:
  *"ditch your flexible modular system, or stay locked into it."* Trinity
  is the third answer — keep the modular stack, add a routing layer that
  learns across it.

MassMutual, ProgressiveRobot, and others have started naming "agent
lock-in" as a procurement concern; Trinity is the architectural response.

## Waitlist

[GitHub Discussions](https://github.com/vishigondi/trinity-local/discussions)
— open an "Interested in Teams" thread, or email teams@keepwhatworks.com.
