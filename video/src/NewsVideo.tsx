import React from 'react';
import {
  AbsoluteFill,
  Img,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from 'remotion';

export interface Segment {
  sentence_text: string;
  image_path: string;
  duration_sec: number;
}

export interface NewsVideoProps {
  runId: string;
  segments?: Segment[];
}

const TextOverlay: React.FC<{text: string; frame: number}> = ({text, frame}) => {
  const {fps} = useVideoConfig();
  
  // Fade in animation
  const opacity = spring({
    frame,
    fps,
    config: {
      damping: 200,
    },
  });
  
  // Scale animation
  const scale = interpolate(frame, [0, 15], [0.8, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div
      style={{
        position: 'absolute',
        bottom: '15%',
        left: '5%',
        right: '5%',
        textAlign: 'center',
        opacity,
        transform: `scale(${scale})`,
      }}
    >
      <div
        style={{
          backgroundColor: 'rgba(0, 0, 0, 0.75)',
          padding: '30px 40px',
          borderRadius: '20px',
          backdropFilter: 'blur(10px)',
        }}
      >
        <p
          style={{
            color: 'white',
            fontSize: '48px',
            fontWeight: 'bold',
            margin: 0,
            lineHeight: 1.4,
            fontFamily: 'Arial, sans-serif',
            textShadow: '2px 2px 8px rgba(0,0,0,0.5)',
          }}
        >
          {text}
        </p>
      </div>
    </div>
  );
};

const SegmentScene: React.FC<{segment: Segment; fps: number}> = ({segment, fps}) => {
  const frame = useCurrentFrame();
  
  return (
    <AbsoluteFill>
      {/* Background Image */}
      <Img
        src={segment.image_path}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
        }}
      />
      
      {/* Dark overlay for better text readability */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'linear-gradient(to top, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0.2) 50%, rgba(0,0,0,0.3) 100%)',
        }}
      />
      
      {/* Text Overlay */}
      <TextOverlay text={segment.sentence_text} frame={frame} />
    </AbsoluteFill>
  );
};

export const NewsVideo: React.FC<NewsVideoProps> = ({segments = []}) => {
  const {fps} = useVideoConfig();
  
  // If no segments provided, show placeholder
  if (segments.length === 0) {
    return (
      <AbsoluteFill
        style={{
          backgroundColor: '#1a1a1a',
          justifyContent: 'center',
          alignItems: 'center',
        }}
      >
        <h1 style={{color: 'white', fontSize: '60px', textAlign: 'center'}}>
          No segments loaded
        </h1>
        <p style={{color: '#999', fontSize: '30px', textAlign: 'center'}}>
          Run generate_segments.py first
        </p>
      </AbsoluteFill>
    );
  }

  let currentFrame = 0;
  
  return (
    <AbsoluteFill>
      {segments.map((segment, index) => {
        const durationInFrames = Math.ceil(segment.duration_sec * fps);
        const sequenceStart = currentFrame;
        currentFrame += durationInFrames;
        
        return (
          <Sequence
            key={index}
            from={sequenceStart}
            durationInFrames={durationInFrames}
          >
            <SegmentScene segment={segment} fps={fps} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
