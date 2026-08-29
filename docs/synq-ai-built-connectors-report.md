# SynQ Connector Plan 


---

## The problem

Today, for every new app (Google, Microsoft, Jira…):

1. We write the code ourselves  
2. We deploy it  
3. Everyone uses our connector  

That works, but every new connector = more work for our team.

---

## The new idea (what your manager suggested)

Like **UPI for banks**:

- We don’t rebuild banking for every bank  
- We make one common “rail”  
- Any bank app can plug into that rail  

For SynQ:

- We make one common **API**  
- We give a simple **guide (MD file)** that Claude / ChatGPT can read  
- AI (or a partner) builds the connector for Jira / Zendesk / etc.  
- That connector sends data to **our API**  
- SynQ still does search, indexing, and chat  

So SynQ stays the brain. Outside people (or AI) build the “plugs.”

---

## Simple picture

```
[ Google / Jira / etc. ]
          |
   connector (AI or partner builds this)
          |
          v
   SynQ public API   ←── we own this
          |
          v
   Index + Chat      ←── we own this
```

---

## Your worries (and short answers)

### 1. “AI will write wrong code”
Yes, often.  
So we must **check** everything with tests and a clear format.  
We never trust AI blindly.

### 2. “Where do env / secrets go?”
- **App secrets** (Google login, Jira login) → stay with whoever runs that connector  
- **SynQ API keys** → we create and give them after registration  
- **Our DB / Qdrant / Gemini keys** → never leave SynQ  

AI should not invent passwords. We issue them.

### 3. “After AI builds it, how does it connect to us?”
Like installing an app:

1. User/partner gets a SynQ connector key from us  
2. Puts that key in their connector  
3. Connector calls our API  
4. We show Connected / Syncing in the UI  

No key = no connection.

### 4. “Is this safe?”
Only if:

- Connectors run **outside** SynQ (not inside our Celery workers)  
- They can only send data for **their tenant**  
- We validate every document  
- We limit how much they can send  

If we let random AI code run inside SynQ → high risk. Don’t do that.

---

## Two ways to work (both can exist)

| Type | Who builds it | Who runs it | Example |
|------|---------------|-------------|---------|
| **Our connectors** | SynQ team | SynQ | Google, Microsoft |
| **Outside connectors** | AI / partner | Their server | Jira, custom ERP |

- Important sources → **we build** (quality + trust)  
- Many small sources later → **outside plugs** (less work for us)

---

## What we recommend

### For now → **don’t change the plan**
Keep building Google / Microsoft the current way.

Why:

- Product quality (chat, sync) matters more right now  
- Microsoft is not fully proven yet  
- The AI/API idea needs a solid public API first  

### Later → **add the UPI-style platform**
When core connectors + chat are stable:

1. Publish a clear SynQ ingest API  
2. Publish a simple MD guide for AI  
3. Let partners/AI build more sources against that API  

---

## One line for your manager

> Good idea for the future. Right now we keep building connectors ourselves. Later we open one API so AI or partners can add more sources — like UPI, SynQ stays the trusted rail.

---

## Don’t do this

- Paste an MD into ChatGPT and put that code straight into production SynQ  
- Give AI our database / embedding / vault secrets  
- Run untrusted connector code inside our workers  

## Do this instead

- Finish first-party connectors (Google, Microsoft, …)  
- Keep our internal document format clean (`UnifiedDocument`)  
- Later turn that into a public API + AI guide  

---

## Bottom line

| Question | Answer |
|----------|--------|
| Is the manager’s idea good? | **Yes, long term** |
| Should we switch now? | **No** |
| What should we do? | **Stick to current architecture; plan the API platform as Phase 2** |
