import { useEffect, useRef } from 'react';

import { store, useDemo } from '../machine/store';
import { run } from '../machine/run';
import { PickStage } from './capture/PickStage';
import { VoiceRecordStage } from './capture/VoiceRecordStage';
import { TypeStage } from './capture/TypeStage';
import { ProcessingStage } from './progress/ProcessingStage';
import { MissingStage } from './result/MissingStage';
import { FinalStage } from './result/FinalStage';

/**
 * Routes the machine's current screen, and starts the run on submit.
 *
 * Four steps: one photo, one voice note, typed answers for anything the
 * voice note left out, and the finished product.
 */
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
          return <PickStage />;
      }

    case 'processing':
      return <ProcessingStage />;

    case 'missing':
      return <MissingStage />;

    case 'final':
      return <FinalStage />;
  }
}
