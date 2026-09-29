import { useCallback, useEffect, useRef, useState } from 'react';

import { copy } from '../../copy/en';
import { MAX_SECONDS, Recorder, RecorderError, micBlockedReason } from '../../audio/recorder';
import { dispatch, useDemo } from '../../machine/store';
import { BigActionButton } from '../widgets/BigActionButton';
import { HoldToSpeakButton } from '../widgets/HoldToSpeakButton';
import { Icon } from '../widgets/Icon';
import { Scaffold } from '../widgets/Scaffold';
import { ScreenHeader } from '../widgets/ScreenHeader';
import { Waveform, WaveformPeaks } from '../widgets/Waveform';
import { VoiceGuide } from './VoiceGuide';
import css from './voice.module.css';

/**
 * Step 2, "Now say what it is": one voice note of at most 30 seconds.
 *
 * The recording is converted to 22.05 kHz mono WAV before it leaves the
 * browser; see src/audio/wav.ts for why that is not optional.
 */
export function VoiceRecordStage() {
  const { voice } = useDemo();
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);

  // Checked before the button is offered rather than after it fails: on
  // plain http there is no microphone to hold down, and pressing a dead
  // button to find that out is a worse way to learn it.
  const blocked = micBlockedReason();

  // The recorder for the press in progress, from the moment of the press:
  // set while getUserMedia is still pending as well as while recording, so a
  // release that arrives before the microphone is up can still reach it.
  const recorderRef = useRef<Recorder | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const stop = useCallback(async () => {
    const rec = recorderRef.current;
    if (!rec) return;
    // Cleared before the conversion below rather than after it, so a new
    // press during the second it takes starts a new recording instead of
    // being swallowed.
    recorderRef.current = null;
    setRecording(false);

    if (!rec.recording) {
      // Released while start() is still waiting on the microphone. This
      // makes that start hand the stream back as soon as it arrives; start
      // then explains what happened.
      rec.cancel();
      return;
    }

    // A newer press may be recording by the time this one has converted;
    // its error and meter are not this clip's to overwrite.
    const latest = () => recorderRef.current === null;
    try {
      const { wav, seconds, peaks } = await rec.stop();
      dispatch({
        t: 'voice',
        voice: { wav, seconds, peaks, url: URL.createObjectURL(wav) },
      });
      if (latest()) setError(null);
    } catch (e) {
      if (latest()) {
        setError(
          e instanceof RecorderError && e.kind === 'tooShort'
            ? copy.voiceTooShort
            : e instanceof Error
              ? e.message
              : copy.voiceFailed,
        );
      }
    } finally {
      if (latest()) {
        setLevel(0);
        setElapsed(0);
      }
    }
  }, []);

  // Must stay synchronous up to rec.start(): that call makes the meter's
  // AudioContext inside the press, which iOS insists on.
  const start = useCallback(async () => {
    // One press at a time. A second start while the first is still waiting
    // on getUserMedia would open a second stream that nothing ever closes.
    if (recorderRef.current) return;
    setError(null);
    const rec = new Recorder({
      onLevel: (l, secs) => {
        setLevel(l);
        setElapsed(secs);
      },
      // Only while this is still the live recorder: after a release its
      // timer ticks on for the moment the stop takes, and must not stop a
      // newer press that has started in that moment.
      onLimit: () => {
        if (recorderRef.current === rec) void stop();
      },
    });
    recorderRef.current = rec;
    try {
      await rec.start();
    } catch (e) {
      if (recorderRef.current === rec) recorderRef.current = null;
      setRecording(false);
      setError(e instanceof Error ? e.message : copy.voiceFailed);
      return;
    }
    if (!rec.recording) {
      // The finger was already off the button when the microphone came up:
      // on a phone the first press opens the permission prompt, which takes
      // the touch away, and a quick tap is over before the microphone
      // answers. Either way the microphone is ready now, and the useful
      // thing to say is how the button works.
      setError(
        'The microphone is ready. Hold the button down while you speak, and let go when you are finished.',
      );
      return;
    }
    setRecording(true);
  }, [stop]);

  // Releasing the mic on unmount matters: a left-running stream keeps the
  // browser's recording indicator lit, which looks like a bug to a judge.
  // cancel() also covers a start still waiting on getUserMedia, which would
  // otherwise open the microphone after the screen has gone.
  useEffect(
    () => () => {
      recorderRef.current?.cancel();
      recorderRef.current = null;
    },
    [],
  );

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

  const shown = Math.min(MAX_SECONDS, Math.floor(elapsed));

  return (
    <Scaffold
      leading="back"
      onLeading={() => dispatch({ t: 'goCapture', stage: 'pick' })}
      step={2}
      stepCount={3}
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
              label={copy.playbackAccept}
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

      <VoiceGuide />
    </Scaffold>
  );
}
