import React from 'react';
import {Composition} from 'remotion';
import {NewsVideo} from './NewsVideo';

export const RemotionRoot: React.FC = () => {
  // Load data from public/data.json if it exists
  const [data, setData] = React.useState<any>(null);
  
  React.useEffect(() => {
    fetch('/data.json')
      .then(res => res.json())
      .then(setData)
      .catch(() => console.log('No data.json found, using defaults'));
  }, []);
  
  const segments = data?.segments || [];
  const totalDuration = segments.reduce((sum: number, s: any) => sum + s.duration_sec, 0);
  const durationInFrames = Math.ceil(totalDuration * 30) || 300;
  
  return (
    <>
      <Composition
        id="NewsVideo"
        component={NewsVideo}
        durationInFrames={durationInFrames}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          segments: segments
        }}
      />
    </>
  );
};
