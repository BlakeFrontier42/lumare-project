# LUMARE MVP - WEEK 1 RESEARCH ENGINE

## TECH STACK
Next.js 15 / Vercel / Tailwind / TypeScript / Zustand

## TASK 1 (48 HOURS): Perplexity Research
1. `/api/research/route.ts` → POST endpoint
   - Model: llama-3.1-sonar-large-128k-online
   - Input: {query: string}
   - Output: {answer: string, sources: array, confidence: number}
   
2. Connect `app/intel/page.tsx`: "Analyze [ticker]" button → research → show answer + sources
   
3. Connect `app/macro/page.tsx`: Auto-query "Current market regime" on load
   
4. Deploy to Vercel

## RULES
- TypeScript + Zod
- Mobile responsive
- Loading states
- Error handling