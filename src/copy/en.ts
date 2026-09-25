/**
 * Every visible string, lifted verbatim from
 * app/lib/l10n/app_en.arb and keyed identically so the two can be diffed.
 *
 * The register is deliberately plain — the app is built for artisans with
 * low literacy, and short declarative sentences are a design decision, not
 * an oversight. Do not "improve" this copy.
 *
 * Keys that do not exist in the app are grouped under `demo` at the bottom:
 * those are the web demo's own scaffolding and are marked as such.
 */

export const copy = {
  // --- voice ---
  voiceTitle: 'Now say what it is',
  voiceBody:
    'What it is, what it is made of, how big it is, how long it took to make, and the price.',
  voiceHoldToSpeak: 'Hold and speak',
  voiceRecording: 'Speaking… let go when you are finished',
  voiceElapsed: (seconds: number, total: number) => `${seconds} of ${total} seconds`,
  voiceTooShort: 'That was very short. Hold the button and speak again.',
  voiceFailed:
    'The microphone did not start. Check that this app is allowed to use it.',
  playbackAccept: 'This is right',

  // --- voice guide (voice_record_stage.dart _guidePoints, in the app's order) ---
  voiceGuideTitle: 'Things you can talk about',
  voiceGuidePoints: [
    'Name of the item', // voiceGuideWhat
    'Colour', // voiceGuideColour
    'Height', // voiceGuideSize
    'Time taken to make it', // voiceGuideTime
    'What the materials cost', // voiceGuideCost
  ],

  // --- queue / progression ---
  queueStateWaiting: 'Waiting for a network',
  queueStateUploading: (percent: number) => `Sending… ${percent} out of a hundred`,
  queueStateProcessing: 'With us now. We are writing it up.',
  queueStateFailed: 'Did not go. Press to see why.',

  // --- needs attention ---
  attentionTitle: 'One question',
  attentionBody: 'We understood everything else. Only this is missing.',
  attentionStartAgain: 'Start again',

  // --- fact sheet field labels ---
  fieldMaterial: 'Made of',
  fieldSize: 'Size',
  fieldColour: 'Colour',
  fieldTechnique: 'How it was made',
  fieldOrigin: 'Where it was made',
  fieldPrice: 'Price',
  correctTypeHint: 'Type the answer here',

  // --- price ---
  priceTitle: 'What is the price?',
  priceBody: 'This is for one piece.',

  // --- misc ---
  actionDone: 'Done',
  listingNoPrice: 'Price not said',

  /**
   * Strings that exist only on the web demo. The server-side pipeline stages
   * have no UI in the app (the phone only ever sees "we are writing it up"),
   * so these are new — written to match the app's register.
   */
  demo: {
    pickTitle: 'Pick a product',
    pickBody: (catalog: boolean) =>
      catalog ? 'Use a photo of your own, or choose one of ours.' : 'Use a photo of your own.',
    pickOwn: 'Use my own photo',
    pickOwnAgain: 'Use a different photo of mine',
    pickCatalog: 'Or choose one',
    pickConfirm: 'Use this photo',
    uploadUnreadable: 'That file could not be opened as a photo. Try a JPEG or PNG.',

    typeInstead: 'Type it instead',
    typeTitle: 'Now write what it is',
    typeHint: 'Type here…',
    typeConfirm: 'Use this description',

    stageImage: 'Cleaning up the photos',
    stageSpeech: 'Listening to what you said',
    stageFactSheet: 'Writing it up',
    stagePrice: 'Working out a fair price',
    stageConfidence: 'Checking it over',

    processingBody: 'This takes about a minute. You do not have to wait here.',
    processingSlow: 'This one is taking a little longer. Nothing is lost.',

    micInsecure:
      'The microphone only works over a secure connection. Open this page with https:// to speak, or type the description instead.',
    micUnsupported:
      'This browser cannot record audio. You can type the description instead.',

    processingFailedTitle: 'That did not work',
    processingFailedAction: 'Start again',

    // --- step 3: what the voice note left out ---
    missingTitle: (n: number) => (n === 1 ? 'One question' : 'A few questions'),
    missingBody: (n: number) =>
      n === 1
        ? 'We understood everything else. Only this is missing.'
        : 'We understood everything else. Only these are missing.',
    missingSkip: 'Leave out anything you do not know.',
    missingMaterial: 'What is it made of?',
    missingSize: 'How big is it?',
    missingSizeHint: 'For example: 9 inches tall',
    missingColour: 'What colour is it?',
    missingOrigin: 'Where was it made?',
    missingOriginHint: 'Village, town or state',
    missingPriceHint: (suggested: string) => `We suggest ${suggested}`,
    missingPriceInvalid: 'Type the price as a number, like 1200.',
    missingConfirm: 'Show my product',
    missingSaveFailed: 'Your answers did not go through. Please try again.',
    photoNote: 'About the photo',

    haltedTitle: 'We could not finish this one',

    // --- step 4: the finished product ---
    finalTitle: 'This is your product',
    finalBody: 'Written from your photo and your voice.',
    finalSuggestedPrice: 'Suggested price',
    finalAnother: 'Make another product',

    demoDataPill: 'Demo data',
    demoDataExplain: (date: string, samePhoto: boolean) =>
      samePhoto
        ? `The live service did not answer in time. This is a recorded run of the same pipeline on this same photo, from ${date}.`
        : `The live service did not answer in time. This is a recorded run of the same pipeline on a different photo, from ${date}.`,
    offlineModelPill: 'Offline model',
    offlineModelExplain:
      'The photo and the voice note went through the real pipeline, but the writing model was unavailable, so the words below come from its offline fallback.',
  },
} as const;

export type Copy = typeof copy;
