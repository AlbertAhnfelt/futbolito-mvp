import { useState, useEffect, useRef } from 'react';
import {
  Layout,
  Typography,
  Select,
  Button,
  Table,
  Alert,
  Card,
  Space,
  Progress,
  Checkbox,
} from 'antd';
import { PlayCircleOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { videoApi } from './services/api';
import type { Highlight, Event, StreamEvent, VideoChunk } from './types';
import { MatchContextForm } from './components/MatchContextForm';
import './App.css';

const { Header, Content, Footer } = Layout;
const { Title, Text } = Typography;

function App() {
  const [videos, setVideos] = useState<string[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<string>('');
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [generatedVideo, setGeneratedVideo] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string>('');

  // NEW: language state
  const [language, setLanguage] = useState<string>('en');
  
  // NEW: graph LLM toggle state
  const [useGraphLLM, setUseGraphLLM] = useState<boolean>(false);

  // Streaming state
  const [chunks, setChunks] = useState<VideoChunk[]>([]);
  const [currentChunkIndex, setCurrentChunkIndex] = useState(0);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState('');
  const [isComplete, setIsComplete] = useState(false);

  // Refs
  const videoRef = useRef<HTMLVideoElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Fetch videos on component mount
  useEffect(() => {
    fetchVideos();
  }, []);

  const fetchVideos = async () => {
    setLoading(true);
    setError('');
    try {
      const videoList = await videoApi.listVideos();
      setVideos(videoList);
    } catch (err) {
      setError('Failed to load videos. Make sure the backend is running.');
      console.error('Error fetching videos:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleAnalyze = () => {
    if (!selectedVideo) {
      setError('Please select a video');
      return;
    }

    // Close any existing EventSource
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    // Reset state
    setAnalyzing(true);
    setError('');
    setHighlights([]);
    setEvents([]);
    setGeneratedVideo('');
    setChunks([]);
    setCurrentChunkIndex(0);
    setProgress(0);
    setStatusMessage('Starting analysis...');
    setIsComplete(false);

    // Create EventSource for streaming with Graph LLM flag
    const eventSource = videoApi.analyzeVideoStream(selectedVideo, useGraphLLM);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      try {
        const data: StreamEvent = JSON.parse(event.data);

        switch (data.type) {
          case 'status':
            console.log('Status:', data.message);
            setStatusMessage(data.message);
            setProgress(data.progress);
            break;

          case 'chunk_ready': {
            console.log('Chunk ready:', data.index, data.url);

            const newChunk: VideoChunk = {
              index: data.index,
              url: `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'}${data.url}`,
              startTime: data.start_time,
              endTime: data.end_time,
            };

            console.log('Full chunk URL:', newChunk.url);

            setChunks((prev) => [...prev, newChunk]);
            setProgress(data.progress);
            break;
          }

          case 'complete':
            console.log('Processing complete:', data.chunks, 'chunks');
            setIsComplete(true);
            setProgress(100);
            setStatusMessage('Complete!');
            setGeneratedVideo(data.final_video);

            // Fetch events (from events.json)
            videoApi
              .getEvents()
              .then((eventsData) => {
                setEvents(eventsData.events || []);
              })
              .catch((err) => {
                console.warn('Could not load events:', err);
              });

            // NEW: Run batch analyze for multi-language commentary/highlights
            videoApi
              .analyzeVideo(selectedVideo, language, useGraphLLM)
              .then((analyzeRes) => {
                if (analyzeRes.highlights) {
                  setHighlights(analyzeRes.highlights);
                }
                if (analyzeRes.generated_video) {
                  setGeneratedVideo(analyzeRes.generated_video);
                }
              })
              .catch((err) => {
                console.warn('Could not run batch analyze for multi-language output:', err);
              });

            eventSource.close();
            setAnalyzing(false);
            break;

          case 'error':
            console.error('Processing error:', data.message);
            setError(`Error: ${data.message}`);
            setStatusMessage(`Error: ${data.message}`);
            eventSource.close();
            setAnalyzing(false);
            break;
        }
      } catch (err) {
        console.error('Error parsing SSE data:', err);
        setError('Error processing streaming response');
      }
    };

    eventSource.onerror = (error) => {
      console.error('EventSource error:', error);
      setError('Connection error during analysis');
      setStatusMessage('Connection error');
      eventSource.close();
      setAnalyzing(false);
    };
  };

  // Handle video ended - play next chunk
  const handleVideoEnded = () => {
    const nextIndex = currentChunkIndex + 1;

    if (nextIndex < chunks.length) {
      const nextChunk = chunks[nextIndex];
      if (videoRef.current) {
        console.log('Playing next chunk:', nextChunk.url);
        videoRef.current.src = nextChunk.url;
        videoRef.current.load();
        videoRef.current.play().catch((err) => {
          console.warn('Error playing next chunk:', err);
        });
      }
      setCurrentChunkIndex(nextIndex);
    } else if (isComplete) {
      console.log('Playback complete');
    } else {
      console.log('Waiting for next chunk...');
    }
  };

  // Set video source when first chunk is available and video element is ready
  useEffect(() => {
    if (chunks.length > 0 && videoRef.current && !videoRef.current.src) {
      const firstChunk = chunks[0];
      console.log('useEffect: Setting video source to first chunk:', firstChunk.url);
      videoRef.current.src = firstChunk.url;
      videoRef.current.load();
      videoRef.current.play().catch((err) => {
        console.warn('Autoplay prevented:', err);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chunks, videoRef.current]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // Columns for events table (left)
  const eventsColumns: ColumnsType<Event> = [
    {
      title: 'Event Time',
      dataIndex: 'time',
      key: 'time',
      width: 100,
    },
    {
      title: 'Event Description',
      dataIndex: 'description',
      key: 'description',
    },
  ];

  // Columns for highlights table (right)
  const highlightsColumns: ColumnsType<Highlight> = [
    {
      title: 'Start Time',
      dataIndex: 'start_time',
      key: 'start_time',
      width: 100,
    },
    {
      title: 'End Time',
      dataIndex: 'end_time',
      key: 'end_time',
      width: 100,
    },
    {
      title: 'Commentary',
      dataIndex: 'commentary',
      key: 'commentary',
      render: (text: string, record: Highlight) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ flex: 1 }}>{text}</span>
          {record.audio_base64 && (
            <audio
              controls
              style={{ height: '32px' }}
              src={`data:audio/mpeg;base64,${record.audio_base64}`}
            />
          )}
        </div>
      ),
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          background: '#1e4d2b',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
        }}
      >
        <ThunderboltOutlined style={{ fontSize: '24px', color: '#6fbf8b', marginRight: '12px' }} />
        <Title level={3} style={{ color: '#fff', margin: 0 }}>
          Futbolito - Football Highlights Analyzer
        </Title>
      </Header>

      <Content style={{ padding: '24px 48px', background: '#f0f9f4' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <MatchContextForm />

          <Card
            style={{ marginBottom: 24, borderRadius: 8 }}
            bordered={false}
          >
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <div>
                <Text strong style={{ fontSize: 16, color: '#1e4d2b' }}>
                  Select a video to analyze
                </Text>
              </div>

              <Space size="middle" style={{ width: '100%' }}>
                {/* Language Select */}
                <Select
                  style={{ width: 160 }}
                  value={language}
                  onChange={setLanguage}
                  disabled={analyzing}
                  options={[
                    { label: 'English', value: 'en' },
                    { label: 'Français', value: 'fr' },
                    { label: 'Español', value: 'es' },
                  ]}
                  size="large"
                />
                
                {/* Graph LLM Toggle */}
                <Checkbox
                  checked={useGraphLLM}
                  onChange={(e) => setUseGraphLLM(e.target.checked)}
                  disabled={analyzing}
                  style={{ whiteSpace: 'nowrap' }}
                >
                  🧠 Dynamic Commentary
                </Checkbox>

                <Select
                  placeholder={
                    loading ? 'Loading videos...' : 'Select a video...'
                  }
                  style={{ minWidth: 300, flex: 1 }}
                  value={selectedVideo || undefined}
                  onChange={setSelectedVideo}
                  loading={loading}
                  disabled={loading || analyzing}
                  options={videos.map((video) => ({
                    label: video,
                    value: video,
                  }))}
                  size="large"
                />

                <Button
                  type="primary"
                  size="large"
                  icon={<PlayCircleOutlined />}
                  onClick={handleAnalyze}
                  loading={analyzing}
                  disabled={!selectedVideo || analyzing}
                  style={{
                    background: '#6fbf8b',
                    borderColor: '#6fbf8b',
                  }}
                >
                  {analyzing ? 'Analyzing...' : 'Analyze Video'}
                </Button>
              </Space>

              {videos.length === 0 && !loading && (
                <Alert
                  message="No videos found"
                  description="Place your .mp4 files in the videos/ folder to analyze them."
                  type="info"
                  showIcon
                />
              )}
            </Space>
          </Card>

          {error && (
            <Alert
              message="Error"
              description={error}
              type="error"
              showIcon
              closable
              onClose={() => setError('')}
              style={{ marginBottom: 24 }}
            />
          )}

          {analyzing && (
            <Card style={{ marginBottom: 24 }}>
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <div>
                  <Text strong style={{ color: '#1e4d2b' }}>
                    {statusMessage || 'Analyzing video...'}
                  </Text>
                </div>
                <Progress
                  percent={progress}
                  status={progress === 100 ? 'success' : 'active'}
                  strokeColor={{
                    '0%': '#6fbf8b',
                    '100%': '#1e4d2b',
                  }}
                />
                {chunks.length > 0 && (
                  <div>
                    <Text type="secondary">
                      Playing chunk {currentChunkIndex + 1} of {chunks.length}
                      {!isComplete && ' (more chunks loading...)'}
                    </Text>
                  </div>
                )}
              </Space>
            </Card>
          )}

          {generatedVideo && !analyzing && (
            <Alert
              message="Video Generated Successfully!"
              description={
                <div>
                  Commentary video has been generated and saved to:{' '}
                  <Text code>{`videos/generated-videos/${generatedVideo}`}</Text>
                </div>
              }
              type="success"
              showIcon
              style={{ marginBottom: 24 }}
            />
          )}

          {(chunks.length > 0 || generatedVideo) && (
            <Card
              title={
                <Title level={4} style={{ margin: 0, color: '#1e4d2b' }}>
                  {isComplete ? 'Generated Commentary Video' : 'Live Streaming Commentary'}
                </Title>
              }
              style={{ borderRadius: 8, marginBottom: 24 }}
            >
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <video
                  ref={videoRef}
                  controls
                  onEnded={handleVideoEnded}
                  onError={(e) => {
                    console.error('Video error:', e);
                    console.error('Video error details:', {
                      error: videoRef.current?.error,
                      networkState: videoRef.current?.networkState,
                      readyState: videoRef.current?.readyState,
                      currentSrc: videoRef.current?.currentSrc,
                    });
                  }}
                  onLoadStart={() => console.log('Video load started')}
                  onLoadedData={() => console.log('Video data loaded')}
                  onCanPlay={() => console.log('Video can play')}
                  style={{ width: '100%', maxWidth: '800px', borderRadius: 8 }}
                >
                  Your browser does not support the video tag.
                </video>
              </div>
              {chunks.length > 0 && (
                <div style={{ marginTop: 16, textAlign: 'center' }}>
                  <Text type="secondary">
                    Chunk {currentChunkIndex + 1} of {chunks.length}
                    {!isComplete && ' - Processing continues in background...'}
                  </Text>
                </div>
              )}
            </Card>
          )}

          {highlights.length > 0 && !analyzing && (
            <Card
              title={
                <Title level={4} style={{ margin: 0, color: '#1e4d2b' }}>
                  Football Highlights & Events
                </Title>
              }
              style={{ borderRadius: 8, marginBottom: 24 }}
            >
              <div style={{ display: 'flex', gap: '16px' }}>
                <div style={{ flex: '0 0 45%' }}>
                  <Title level={5} style={{ color: '#1e4d2b', marginBottom: 12 }}>
                    Detected Events
                  </Title>
                  <Table
                    columns={eventsColumns}
                    dataSource={events}
                    rowKey={(record, index) => `event-${index}`}
                    pagination={false}
                    scroll={{ y: 400 }}
                    size="small"
                  />
                </div>

                <div style={{ flex: '0 0 55%' }}>
                  <Title level={5} style={{ color: '#1e4d2b', marginBottom: 12 }}>
                    Generated Commentary
                  </Title>
                  <Table
                    columns={highlightsColumns}
                    dataSource={highlights}
                    rowKey={(record, index) => `highlight-${index}`}
                    pagination={false}
                    scroll={{ y: 400 }}
                    size="small"
                  />
                </div>
              </div>
            </Card>
          )}
        </div>
      </Content>

      <Footer style={{ textAlign: 'center', background: '#f0f9f4' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          Team 7: Jayden Caixing Piao, Salah Eddine Nifa, Albert Ahnfelt,
          Antoine Fauve, Lucas Rulland, Hyun Suk Kim
        </Text>
      </Footer>
    </Layout>
  );
}

export default App;
