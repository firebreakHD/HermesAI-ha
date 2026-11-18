// Keep the remote WebRTC tracks and the synthetic microphone on separate graphs.
(() => {
    if (window !== window.top || !navigator.mediaDevices) return;
    const captured = [];
    const tracks = new Set();
    let context, microphone, playing, revision = 0;
    let connectedPeers = 0;
    function setup() {
        if (!context) {
            context = new AudioContext({sampleRate: 16000});
            microphone = context.createMediaStreamDestination();
        }
        return context.resume();
    }
    const getUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (constraints) => {
        if (!constraints.audio) return getUserMedia(constraints);
        await setup();
        // Talk is free to enable, disable and dispose of its copy of the track.
        const output = new MediaStream([microphone.stream.getAudioTracks()[0].clone()]);
        if (constraints.video) {
            const video = await getUserMedia({video: constraints.video});
            for (const track of video.getVideoTracks()) output.addTrack(track);
        }
        return output;
    };

    const RTC = window.RTCPeerConnection;
    window.RTCPeerConnection = new Proxy(RTC, {
        construct(target, args) {
            const pc = Reflect.construct(target, args);
            let connected = false;
            pc.addEventListener("connectionstatechange", () => {
                const active = pc.connectionState === "connected";
                connectedPeers += Number(active) - Number(connected);
                connected = active;
            });
            pc.addEventListener("track", ({track}) => {
                if (track.kind !== "audio" || tracks.has(track)) return;
                tracks.add(track);
                void setup();
                const source = context.createMediaStreamSource(new MediaStream([track]));
                const processor = context.createScriptProcessor(2048, 1, 1);
                const mute = context.createGain();
                mute.gain.value = 0;
                processor.onaudioprocess = (event) => {
                    if (pc.connectionState !== "connected" || track.muted) return;
                    const input = event.inputBuffer.getChannelData(0);
                    const pcm = new DataView(new ArrayBuffer(input.length * 2));
                    for (let i = 0; i < input.length; i++) {
                        const sample = Math.round(input[i] * 32768);
                        pcm.setInt16(i * 2, Math.max(-32768, Math.min(32767, sample)), true);
                    }
                    if (captured.length >= 40) captured.shift();
                    captured.push(btoa(String.fromCharCode(...new Uint8Array(pcm.buffer))));
                };
                source.connect(processor).connect(mute).connect(context.destination);
                const cleanup = () => {
                    processor.onaudioprocess = null;
                    source.disconnect();
                    processor.disconnect();
                    mute.disconnect();
                    tracks.delete(track);
                };
                track.addEventListener("ended", cleanup, {once: true});
            });
            return pc;
        },
    });

    function stop() {
        revision++;
        if (playing) {
            playing.stop();
            playing = undefined;
        }
    }
    window.hermesMedia = {
        drain: () => ({connected: connectedPeers > 0, pcm: captured.splice(0)}),
        stop,
        async play(encoded) {
            stop();
            const current = revision;
            await setup();
            const bytes = Uint8Array.from(atob(encoded), (value) => value.charCodeAt(0));
            const buffer = await context.decodeAudioData(bytes.buffer);
            if (revision !== current) return;
            const node = context.createBufferSource();
            node.buffer = buffer;
            node.connect(microphone);
            node.onended = () => {
                node.disconnect();
                if (playing === node) playing = undefined;
            };
            playing = node;
            node.start();
        },
    };
})();
