# GPT Photo Reorder Token Limit Fix

**Date:** 29/01/2026, Wednesday, 4:31 PM (Brisbane Time)

## Problem

The photo reordering system was consistently receiving empty responses from the GPT API with `finish_reason='length'`, indicating that responses were being truncated due to token limits.

### Symptoms
- All GPT API calls returned empty content
- `finish_reason='length'` in all responses
- 640 reasoning tokens consumed, leaving 0 tokens for actual response content
- System falling back to alternate models (gpt-4.1-mini) which also had token limits
- Properties failing to get photo tours created

### Root Cause
The `gpt-5-nano-2025-08-07` model was using all available tokens for reasoning (640 tokens) with the `max_completion_tokens` parameter set to 640-768, leaving no tokens for the actual JSON response content.

## Solution

Removed all `max_completion_tokens` limits from the GPT API calls to allow unlimited token generation for responses.

### Changes Made

**File:** `/Users/projects/Documents/Property_Data_Scraping/01_House_Plan_Data/src/gpt_reorder_client.py`

1. **Primary API Call** (line ~230)
   - **Before:** `max_completion_tokens=768`
   - **After:** Removed parameter entirely

2. **Fallback API Call** (line ~260)
   - **Before:** `max_completion_tokens=640`
   - **After:** Removed parameter entirely

3. **Alternate Model Fallback** (line ~290)
   - **Before:** `max_completion_tokens=640`
   - **After:** Removed parameter entirely

## Technical Details

### Why This Works
- The `gpt-5-nano` model uses reasoning tokens internally before generating the response
- With a hard limit of 640-768 tokens, the model exhausted all tokens on reasoning
- Removing the limit allows the model to use as many tokens as needed for both reasoning and response generation
- The API will still respect the model's maximum context window, but won't artificially truncate responses

### Fallback Strategy Preserved
The system still maintains its robust fallback strategy:
1. Primary attempt with JSON mode
2. Fallback without response_format if empty
3. Alternate model (gpt-4.1-mini) if still empty
4. Chunked processing if full-set fails

## Testing

To test the fix, run the photo reordering system:

```bash
cd /Users/projects/Documents/Property_Data_Scraping/01_House_Plan_Data && python src/photo_reorder_parallel.py
```

### Expected Results
- GPT responses should now contain full JSON content
- No more `finish_reason='length'` errors
- Properties should successfully get photo tours created
- Reduced reliance on alternate model fallbacks

## Impact

- **Positive:** Photo reordering will now work correctly for all properties
- **Cost:** May increase token usage per request, but ensures successful completions
- **Performance:** Should reduce the need for fallback attempts and chunking

## Related Files
- `/Users/projects/Documents/Property_Data_Scraping/01_House_Plan_Data/src/gpt_reorder_client.py` - Main fix
- `/Users/projects/Documents/Property_Data_Scraping/01_House_Plan_Data/src/photo_reorder_parallel.py` - Coordinator
- `/Users/projects/Documents/Property_Data_Scraping/01_House_Plan_Data/src/worker_reorder.py` - Worker implementation

## Notes

- The `MAX_TOKENS` config variable is still imported but no longer used in this client
- Consider removing the import if not used elsewhere
- Monitor API costs after deployment to ensure token usage is reasonable
