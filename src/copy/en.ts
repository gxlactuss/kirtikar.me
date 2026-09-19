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
  // --- capture ---
  captureTitle: 'Add a product',
  capturePhotoStep: (current: number, total: number) => `Photo ${current} of ${total}`,
  capturePhotoWhole: 'Show the whole product',
  capturePhotoDetail: 'Take one from close up',
  capturePhotoScale: 'Put a hand beside it, so the size shows',
  captureFromGallery: 'Choose from gallery',

  shotReviewChecking: 'Checking the photo…',
  shotReviewRetake: 'Take it again',

  photoSetTitle: 'Your three photos',
  photoSetBody:
    'The first photo is the one buyers see first. Press a photo to take it again.',
  photoSetMain: 'First photo',
  photoSetConfirm: 'These photos are good',

  photoIssueTooDark: 'Too dark to see clearly',
  photoIssueTooBright: 'Too much light on it',
  photoIssueBlurry: 'Blurry, not clear enough',
  photoIssueNoSubject: 'No product seen in this photo',
  photoIssueOutOfFrame: 'Product not fully in the photo',

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
  voiceBackToPhotos: 'Back to the photos',

  // --- saved ---
  savedTitle: 'Saved',
  savedBodyOnline: 'It is being sent now. You do not have to wait here.',
  savedAddAnother: 'Add another product',
  savedGoHome: 'Go to the home screen',

  // --- queue / progression ---
  queueStateWaiting: 'Waiting for a network',
  queueStateUploading: (percent: number) => `Sending… ${percent} out of a hundred`,
  queueStateProcessing: 'With us now. We are writing it up.',
  queueStateFailed: 'Did not go. Press to see why.',

  // --- needs attention ---
  attentionTitle: 'One question',
  attentionBody: 'We understood everything else. Only this is missing.',
  attentionRetakePhotos: 'Take the photos again',

  // --- read back ---
  readBackTitle: 'This is what we understood',
  readBackFields: 'What we wrote down',
  readBackCorrect: 'Press anything that is wrong',
  readBackApprove: 'All of this is right',

  // --- fact sheet field labels ---
  fieldMaterial: 'Made of',
  fieldSize: 'Size',
  fieldColour: 'Colour',
  fieldTechnique: 'How it was made',
  fieldOrigin: 'Where it was made',
  fieldQuantity: 'How many',
  fieldPrice: 'Price',
  correctTypeHint: 'Type the answer here',

  // --- suggestions ---
  suggestTitle: 'Shall we add this?',
  suggestYes: 'Yes, add it',
  suggestNo: 'No, leave it out',
  suggestSkip: 'I am not sure',
  suggestProgress: (current: number, total: number) => `${current} of ${total}`,

  // --- price ---
  priceTitle: 'What is the price?',
  priceBody: 'This is for one piece.',
  priceFloor: (amount: string) => `What it cost you: ${amount}`,
  priceFloorExplain:
    'Your materials and your time come to this much. Selling below it means you lose money on the work.',
  priceBand: (low: string, high: string) =>
    `Others sell this kind of thing for ${low} to ${high}`,
  priceBelowFloor: 'This is below what it cost you to make. You can still choose it.',
  priceConfirm: 'This price is right',

  // --- stock ---
  stockTitle: 'How many do you have?',
  stockBody: 'When they are all sold, we take the listing down for you.',
  stockOneOfAKind: 'There is only one, and there will never be another',
  stockMore: 'One more',
  stockLess: 'One less',

  // --- photos / preview ---
  photosTitle: 'Which photo comes first?',
  previewTitle: 'This is what buyers will see',

  // --- consent ---
  consentTitle: 'May we put this up for sale?',
  consentPhoto: 'Show my photos',
  consentPhotoExplain: "The photographs of your product go on the buyer's screen.",
  consentStory: 'Show my craft story',
  consentStoryExplain:
    'Your name, your village and how you make things go on the maker card. You can say no and still sell.',
  consentNeeded: 'We cannot put it up without the photos.',
  consentPublish: 'Put it up for sale',

  // --- publishing ---
  publishingTitle: 'Putting it up for sale',
  publishingBody: 'This takes a moment. Do not close the app.',
  publishedTitle: 'It is up for sale',
  publishedBody: 'Buyers can see it now.',
  publishedShare: 'Send it on WhatsApp',
  publishedCopyLink: 'Copy the link',
  publishedLinkCopied: 'The link is copied',
  publishedQrExplain: 'Anyone can point their phone at this to open your product.',
  publishedAnother: 'Make another like this',
  publishedDone: 'Go to the home screen',
  publishFailed: 'It could not be put up. Nothing is lost — you can try again.',
  publishRetry: 'Try again',

  // --- misc ---
  actionDone: 'Done',
  listingNoPrice: 'Price not said',
  notSaid: 'Not said',

  /**
   * Strings that exist only on the web demo. The server-side pipeline stages
   * have no UI in the app (the phone only ever sees "we are writing it up"),
   * so these are new — written to match the app's register.
   */
  demo: {
    pickTitle: 'Pick a product',
    pickBody: 'Choose a photo, or use one of your own.',
    pickOwn: 'Use my own photo',
    pickConfirm: 'Use these photos',
    pickCount: (n: number) => (n === 1 ? '1 photo chosen' : `${n} photos chosen`),

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

    processingFailedTitle: 'That did not work',
    processingFailedAction: 'Start again',

    demoDataPill: 'Demo data',
    demoDataExplain: (date: string) =>
      `The live service did not answer in time. This is a recorded run of the same pipeline on this same photo, from ${date}.`,
    offlineModelPill: 'Offline model',
  },
} as const;

export type Copy = typeof copy;
