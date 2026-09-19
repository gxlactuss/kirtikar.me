import type { ReactNode } from 'react';

import { copy } from '../../copy/en';
import { stepOf, STEP_COUNT } from '../../machine/reducer';
import { dispatch, useDemo } from '../../machine/store';
import { Scaffold } from '../widgets/Scaffold';
import { ScreenHeader } from '../widgets/ScreenHeader';

interface Props {
  title: string;
  subtitle?: string;
  children?: ReactNode;
  actions?: ReactNode;
}

/**
 * Shared chrome for the wizard: back arrow, step bar, header.
 *
 * The step count stays at 7 even when the suggestions stage is skipped,
 * because that is what ReviewController does — the bar describes the journey,
 * not the subset this particular listing happens to take.
 */
export function ReviewScaffold({ title, subtitle, children, actions }: Props) {
  const { screen, provenance } = useDemo();
  const stage = screen.name === 'review' ? screen.stage : 'readBack';
  const step = stepOf(stage);

  const pill =
    provenance?.kind === 'fixture'
      ? copy.demo.demoDataPill
      : provenance?.kind === 'live' && !provenance.usedLiveModel
        ? copy.demo.offlineModelPill
        : null;

  return (
    <Scaffold
      leading="back"
      onLeading={() => dispatch({ t: 'reviewBack' })}
      step={step > 0 ? step : undefined}
      stepCount={step > 0 ? STEP_COUNT : undefined}
      actions={actions}
      pill={pill}
    >
      <ScreenHeader title={title} subtitle={subtitle} />
      {children}
    </Scaffold>
  );
}
