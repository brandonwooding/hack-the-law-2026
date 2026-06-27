export interface Regime {
  id: string;
  name: string;
  shortDescription: string;
  confirmed: boolean;
  summary: string;
  scope: string;
  process: string;
  consequence: string;
  obligations: { text: string; reference: string }[];
  guidance: string;
}

export const seedRegimes: Regime[] = [
  {
    id: "online-safety-act-2023",
    name: "Online Safety Act 2023",
    shortDescription: "Imposes duties of care on online platforms hosting user content",
    confirmed: false,
    summary:
      "The Online Safety Act 2023 establishes a regulatory framework for user-to-user and search services, requiring them to manage risks arising from illegal content and, for certain services, content that is harmful to children. Ofcom is the appointed regulator with broad information-gathering and enforcement powers. The regime is being phased in through codes of practice and risk-assessment duties.",
    scope:
      "Applies to providers of regulated user-to-user services and search services with links to the United Kingdom, regardless of where the provider is established. This captures social media, messaging, file-sharing, gaming and many search platforms. Additional duties attach to services likely to be accessed by children and to categorised (high-reach) services.",
    process:
      "Ofcom regulates through binding codes of practice, mandatory illegal-content and children's risk assessments, and transparency reporting. Providers must keep records of their assessments and demonstrate proportionate safety measures. Ofcom can issue information notices, require independent audits, and open investigations where it suspects non-compliance.",
    consequence:
      "Non-compliance can result in fines of up to £18 million or 10% of qualifying worldwide revenue, whichever is greater. In serious cases Ofcom may seek business-disruption measures, including service-restriction orders against third parties such as payment and advertising providers. Senior managers may face criminal liability for failing to comply with certain information requirements.",
    obligations: [
      {
        text: "Carry out and keep up to date suitable illegal-content risk assessments",
        reference: "see: Ofcom v. Meridian Social Ltd, 2024",
      },
      {
        text: "Implement proportionate systems to mitigate identified risks of illegal content",
        reference: "see: R (Safeguard NGO) v. Ofcom, 2024",
      },
      {
        text: "Operate accessible reporting and complaints mechanisms for users",
        reference: "see: Ofcom Enforcement Decision 2024/11",
      },
      {
        text: "Protect children from harmful content where the service is likely to be accessed by them",
        reference: "see: Ofcom v. PlayStream UK, 2025",
      },
    ],
    guidance:
      "Begin with a documented illegal-content risk assessment, as this anchors every downstream duty and is the first thing Ofcom will request. Map your service against the relevant codes of practice early, and retain evidence of the proportionality of each measure adopted — Ofcom's enforcement posture favours demonstrable process over perfection.",
  },
  {
    id: "uk-gdpr-dpa-2018",
    name: "UK GDPR / Data Protection Act 2018",
    shortDescription: "Governs the processing of personal data",
    confirmed: false,
    summary:
      "The UK GDPR, supplemented by the Data Protection Act 2018, governs how organisations collect, use, store and share personal data relating to individuals in the United Kingdom. It is enforced by the Information Commissioner's Office (ICO). The regime is principles-based and applies across virtually every sector that handles personal data.",
    scope:
      "Applies to controllers and processors handling personal data of individuals in the UK, including organisations established outside the UK that offer goods or services to, or monitor, UK individuals. Online safety contexts frequently engage it through age-assurance, content moderation, and user-reporting data flows.",
    process:
      "The ICO enforces through audits, assessment notices, and investigations, often prompted by complaints or data-breach reports. Controllers must maintain records of processing, conduct Data Protection Impact Assessments for high-risk activities, and report qualifying breaches within 72 hours. The ICO favours a graduated approach, escalating from guidance to formal action.",
    consequence:
      "Maximum fines reach £17.5 million or 4% of total annual worldwide turnover, whichever is higher, for the most serious infringements. The ICO may also issue enforcement notices compelling or prohibiting specific processing, and individuals may bring compensation claims for material or non-material damage.",
    obligations: [
      {
        text: "Identify a lawful basis for each processing activity",
        reference: "see: ICO v. Datapoint Analytics, 2023",
      },
      {
        text: "Provide clear, accessible privacy information to data subjects",
        reference: "see: ICO Enforcement Notice 2024/07",
      },
      {
        text: "Apply data protection by design and by default, including for age assurance",
        reference: "see: Re Children's Code Compliance, 2024",
      },
      {
        text: "Report qualifying personal-data breaches to the ICO within 72 hours",
        reference: "see: ICO v. Northgate Retail, 2023",
      },
    ],
    guidance:
      "Where online safety measures rely on processing personal data — age verification, behavioural monitoring, or content review — document the lawful basis and a DPIA before launch. The ICO's Children's Code is particularly relevant to services accessed by minors and should be read alongside the Online Safety Act duties rather than in isolation.",
  },
  {
    id: "communications-act-2003",
    name: "Communications Act 2003",
    shortDescription: "Underpins Ofcom's powers over electronic communications and media",
    confirmed: false,
    summary:
      "The Communications Act 2003 establishes Ofcom and confers its core regulatory powers over electronic communications networks, services and broadcasting. It remains the structural foundation on which the Online Safety Act's enforcement machinery is built. Several offences and information powers relevant to online conduct also sit within this Act.",
    scope:
      "Applies to providers of electronic communications networks and services, broadcasters, and, through specific provisions, individuals who send communications. Its relevance to online safety lies primarily in Ofcom's institutional powers and in offences relating to improper use of public communications networks.",
    process:
      "Ofcom administers licensing, sets and enforces conditions on communications providers, and investigates breaches using statutory information powers. Enforcement typically proceeds through notification of contravention, an opportunity to make representations, and then penalty or direction where a breach is confirmed.",
    consequence:
      "Penalties vary by provision but can include substantial financial penalties for regulated providers and criminal sanctions for certain communications offences. Ofcom may also vary, suspend or revoke entitlements to provide regulated services in serious cases.",
    obligations: [
      {
        text: "Comply with applicable general conditions of entitlement set by Ofcom",
        reference: "see: Ofcom v. ClearLine Telecom, 2022",
      },
      {
        text: "Respond fully and promptly to statutory information requests",
        reference: "see: Ofcom Decision 2023/19",
      },
      {
        text: "Refrain from sending messages that are grossly offensive or menacing via public networks",
        reference: "see: R v. Holloway, 2021",
      },
    ],
    guidance:
      "Treat this Act as the procedural backbone behind Ofcom's online-safety enforcement rather than a standalone compliance target for most platforms. Where your service also operates as a communications provider, confirm which general conditions apply, as these run in parallel to any online-safety duties.",
  },
];
