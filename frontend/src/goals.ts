export type ResearchGoal =
  'business' | 'key_risks' | 'management_analysis' | 'market_risk' | 'legal_regulatory_risk';

export const goals: Record<
  ResearchGoal,
  { label: string; guidance: string; examples: readonly [string, string, string] }
> = {
  business: {
    label: 'Business',
    guidance: 'Explore the company’s business model, customers, products, and dependencies.',
    examples: [
      'How does the company make money, and which products or services matter most?',
      'Who are the company’s principal customers and distribution channels?',
      'What competitive strengths and business dependencies does the company describe?',
    ],
  },
  key_risks: {
    label: 'Key Risks',
    guidance: 'Synthesize material risks disclosed in the filing.',
    examples: [
      'Which disclosed risks could materially affect the company’s operations or financial results?',
      'What important suppliers, platforms, customers, or other dependencies create risk?',
      'How does the company describe its cybersecurity and operational-resilience risks?',
    ],
  },
  management_analysis: {
    label: 'Management Analysis',
    guidance: 'Examine management’s account of performance, liquidity, and trends.',
    examples: [
      'What factors does management say drove the latest changes in revenue and profitability?',
      'How does management assess liquidity, capital resources, and funding needs?',
      'Which trends and uncertainties does management identify for future operating results?',
    ],
  },
  market_risk: {
    label: 'Market Risk',
    guidance: 'Review quantified market exposures and how they are managed.',
    examples: [
      'What exposure does the company have to interest-rate, currency, equity, or commodity risk?',
      'How does the company quantify and manage its market-risk exposures?',
      'What does the company’s sensitivity analysis indicate about potential market impacts?',
    ],
  },
  legal_regulatory_risk: {
    label: 'Legal and Regulatory Risk',
    guidance: 'Review disclosed proceedings, investigations, and regulatory exposure.',
    examples: [
      'What material legal proceedings or regulatory matters does the company disclose?',
      'How could changing laws or regulation affect the company’s business?',
      'What litigation, investigation, compliance, or loss-contingency risks are described?',
    ],
  },
};

export const goalEntries = Object.entries(goals) as [ResearchGoal, (typeof goals)[ResearchGoal]][];
