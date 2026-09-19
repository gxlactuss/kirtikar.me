import { useEffect, useRef } from 'react';

import { store, useDemo } from '../machine/store';
import { run } from '../machine/run';
import { PhotoSetStage } from './capture/PhotoSetStage';
import { VoiceRecordStage } from './capture/VoiceRecordStage';
import { TypeStage } from './capture/TypeStage';
import { ProcessingStage } from './progress/ProcessingStage';
import { NeedsAttentionStage } from './review/NeedsAttentionStage';
import { ReadBackStage } from './review/ReadBackStage';
import { SuggestionsStage } from './review/SuggestionsStage';
import { PriceStage } from './review/PriceStage';
import { StockStage } from './review/StockStage';
import { PhotosStage } from './review/PhotosStage';
import { PreviewStage } from './review/PreviewStage';
import { ConsentStage } from './review/ConsentStage';
import { PublishStage } from './review/PublishStage';

/** Routes the machine's current screen, and starts the run on submit. */
export function DemoApp() {
  const { screen } = useDemo();
  const started = useRef(false);

  useEffect(() => {
    if (screen.name !== 'processing' || started.current) return;
    started.current = true;

    const controller = new AbortController();
    void run(store, controller.signal);
    return () => controller.abort();
  }, [screen.name]);

  // Re-arm for the next product once we are back at the start.
  useEffect(() => {
    if (screen.name === 'capture') started.current = false;
  }, [screen.name]);

  switch (screen.name) {
    case 'capture':
      switch (screen.stage) {
        case 'voiceRecord':
          return <VoiceRecordStage />;
        case 'typing':
          return <TypeStage />;
        default:
          return <PhotoSetStage />;
      }

    case 'processing':
      return <ProcessingStage />;

    case 'review':
      switch (screen.stage) {
        case 'needsAttention':
          return <NeedsAttentionStage />;
        case 'readBack':
          return <ReadBackStage />;
        case 'suggestions':
          return <SuggestionsStage />;
        case 'price':
          return <PriceStage />;
        case 'stock':
          return <StockStage />;
        case 'photos':
          return <PhotosStage />;
        case 'preview':
          return <PreviewStage />;
        case 'consent':
          return <ConsentStage />;
        case 'publishing':
          return <PublishStage />;
      }
      return <ReadBackStage />;

    case 'published':
      return <PublishStage />;
  }
}
