import { useCallback, useEffect, useRef, useState } from 'react';

import { copy } from '../../copy/en';
import { MAX_SECONDS, Recorder, RecorderError, micBlockedReason } from '../../audio/recorder';
import { CRAFT_BY_SLUG } from '../crafts';
import { dispatch, useDemo } from '../../machine/store';
import { BigActionButton } from '../widgets/BigActionButton';
import { HoldToSpeakButton } from '../widgets/HoldToSpeakButton';
import { Icon } from '../widgets/Icon';
import { Scaffold } from '../widgets/Scaffold';
import { ScreenHeader } from '../widgets/ScreenHeader';
import { Waveform, WaveformPeaks } from '../widgets/Waveform';
import css from './voice.module.css';

/**
 * "Now say what it is" — the heart of the app.
 *
 * The recording is converted to 22.05 kHz mono WAV before it leaves the
 * browser; see src/audio/wav.ts for why that is not optional.
 */
export function VoiceRecordStage() {
  const { photos, voice } = useDemo();
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);

  // Checked before the button is offered rather than after it fails: on
  // plain http there is no microphone to hold down, and pressing a dead
  // button to find that out is a worse way to learn it.
  const blocked = micBlockedReason();

  const recorderRef = useRef<Recorder | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const stop = useCallback(async () => {
    const rec = recorderRef.current;
    if (!rec?.recording) return;
    setRecording(false);
    try {
      const { wav, seconds, peaks } = await rec.stop();
      dispatch({
        t: 'voice',
        voice: { wav, seconds, peaks, url: URL.createObjectURL(wav) },
      });
      setError(null);
    } catch (e) {
      setError(
        e instanceof RecorderError && e.kind === 'tooShort'
          ? copy.voiceTooShort
          : e instanceof Error
            ? e.message
            : copy.voiceFailed,
      );
    } finally {
      setLevel(0);
      setElapsed(0);
    }
  }, []);

  const start = useCallback(async () => {
    setError(null);
    const rec = new Recorder({
      onLevel: (l, secs) => {
        setLevel(l);
        setElapsed(secs);
      },
      onLimit: () => void stop(),
    });
    recorderRef.current = rec;
    try {
      await rec.start();
      setRecording(true);
    } catch (e) {
      setRecording(false);
      setError(e instanceof Error ? e.message : copy.voiceFailed);
    }
  }, [stop]);

  // Releasing the mic on unmount matters: a left-running stream keeps the
  // browser's recording indicator lit, which looks like a bug to a judge.
  useEffect(() => () => recorderRef.current?.cancel(), []);

  const togglePlay = () => {
    const el = audioRef.current;
    if (!el) return;
    if (playing) {
      el.pause();
      el.currentTime = 0;
      setPlaying(false);
    } else {
      void el.play();
      setPlaying(true);
    }
  };

  const hint = photos[0] ? CRAFT_BY_SLUG.get(photos[0].slug)?.hint : undefined;
  const shown = Math.min(MAX_SECONDS, Math.floor(elapsed));

  return (
    <Scaffold
      leading="back"
      onLeading={() => dispatch({ t: 'goCapture', stage: 'photoSet' })}
      step={2}
      stepCount={2}
      actions={
        <>
          {blocked ? null : (
            <HoldToSpeakButton
              recording={recording}
              label={recording ? copy.voiceRecording : copy.voiceHoldToSpeak}
              onStart={() => void start()}
              onStop={() => void stop()}
            />
          )}
          {voice ? (
            <BigActionButton
              label="This is right"
              icon="check"
              onClick={() => dispatch({ t: 'submit' })}
            />
          ) : null}
          <BigActionButton
            label={copy.demo.typeInstead}
            icon="keyboard"
            tone="secondary"
            onClick={() => dispatch({ t: 'goCapture', stage: 'typing' })}
          />
        </>
      }
    >
      <ScreenHeader title={copy.voiceTitle} subtitle={copy.voiceBody} />

      {hint ? (
        <div className={css.prompt}>
          <p className={css.promptLabel}>Something you could say</p>
          <p className={css.promptText}>“{hint}”</p>
        </div>
      ) : null}

      <Waveform level={recording ? level : 0} active={recording} />

      <p className={`${css.elapsed} ${recording ? css.elapsedActive : ''}`}>
        {copy.voiceElapsed(shown, MAX_SECONDS)}
      </p>

      {blocked ? (
        <div className={css.error}>
          <Icon name="error_outline" size={22} className={css.errorIcon} />
          <span>{blocked === 'insecure' ? copy.demo.micInsecure : copy.demo.micUnsupported}</span>
        </div>
      ) : null}

      {error ? (
        <div className={css.error}>
          <Icon name="error_outline" size={22} className={css.errorIcon} />
          <span>{error}</span>
        </div>
      ) : null}

      {voice && !recording ? (
        <>
          <WaveformPeaks peaks={voice.peaks} />
          <div className={css.playbackRow}>
            <button
              type="button"
              className={css.playButton}
              onClick={togglePlay}
              aria-label={playing ? 'Stop playback' : 'Play what you said'}
            >
              <Icon name={playing ? 'stop' : 'play_arrow'} size={28} />
            </button>
            <span className={css.playMeta}>
              <strong>What you said</strong>
              {voice.seconds.toFixed(1)} seconds
            </span>
          </div>
          <audio
            ref={audioRef}
            src={voice.url}
            onEnded={() => setPlaying(false)}
            hidden
          />
        </>
      ) : null}
    </Scaffold>
  );
}
