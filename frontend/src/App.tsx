import { useState, useEffect, useRef } from 'react';
import {
  Layout,
  Typography,
  Select,
  Button,
  Table,
  Alert,
  Spin,
  Card,
  Space,
  Progress,
  Radio,
  Input, // <--- Imported Input
  message, // <--- Imported message for notifications
} from 'antd';
import { PlayCircleOutlined, ThunderboltOutlined, SendOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { videoApi, commentApi } from './services/api';
import type { Highlight, Event, StreamEvent, VideoChunk } from './types';
import { MatchContextForm } from './components/MatchContextForm';
import './App.css';

const { Header, Content, Footer } = Layout;
const { Title, Text } = Typography;
const { TextArea } = Input; // <--- Destructure TextArea

function App() {
  const [videos, setVideos] = useState<string[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<string>('');
  const [language, setLanguage] = useState<string>('English');
  
  // Feedback State
  const [userComment, setUserComment] = useState('');
  const [submittingComment, setSubmittingComment] = useState(false);

  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [generatedVideo, setGeneratedVideo] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string>('');

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

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setAnalyzing(true);
    setError('');
    setHighlights([]);
    setEvents([]);
    setGeneratedVideo('');
    setChunks([]);
    setCurrentChunkIndex(0);
    setProgress(0);
    setStatusMessage(`Starting analysis in ${language}...`);
    setIsComplete(false);

    // Note: Ensure your backend accepts the language parameter if needed
    const eventSource = videoApi.analyzeVideoStream(selectedVideo,language);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      try {
        const data: StreamEvent = JSON.parse(event.data);

        switch (data.type) {
          case 'status':
            setStatusMessage(data.message);
            setProgress(data.progress);
            break;

          case 'chunk_ready':
            const newChunk: VideoChunk = {
              index: data.index,
              url: `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'}${data.url}`,
              startTime: data.start_time,
              endTime: data.end_time,
            };
            setChunks((prev) => [...prev, newChunk]);
            setProgress(data.progress);
            break;

          case 'complete':
            setIsComplete(true);
            setProgress(100);
            setStatusMessage('Complete!');
            setGeneratedVideo(data.final_video);
            
            videoApi.getEvents()
              .then((eventsData) => setEvents(eventsData.events || []))
              .catch((err) => console.warn('Could not load events:', err));

            eventSource.close();
            setAnalyzing(false);
            break;

          case 'error':
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

  const handleVideoEnded = () => {
    const nextIndex = currentChunkIndex + 1;
    if (nextIndex < chunks.length) {
      const nextChunk = chunks[nextIndex];
      if (videoRef.current) {
        videoRef.current.src = nextChunk.url;
        videoRef.current.load();
        videoRef.current.play().catch((err) => console.warn('Error playing next chunk:', err));
      }
      setCurrentChunkIndex(nextIndex);
    }
  };

  useEffect(() => {
    if (chunks.length > 0 && videoRef.current && !videoRef.current.src) {
      const firstChunk = chunks[0];
      videoRef.current.src = firstChunk.url;
      videoRef.current.load();
      videoRef.current.play().catch((err) => console.warn('Autoplay prevented:', err));
    }
  }, [chunks, videoRef.current]);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // New function to handle comment submission
  const handleSubmitComment = async () => {
    if (!userComment.trim()) {
      message.warning('Please write a comment before sending.');
      return;
    }

    setSubmittingComment(true);
    try {
      await commentApi.sendComment({
        comment: userComment,
        video: selectedVideo,
        timestamp: new Date().toISOString()
      });

      message.success('Thank you! Your feedback has been sent.');
      setUserComment('');
    } catch (error) {
      console.error('Error sending feedback:', error);
      message.error('Network error. Could not send feedback.');
    } finally {
      setSubmittingComment(false);
    }
  };

  const eventsColumns: ColumnsType<Event> = [
    { title: 'Event Time', dataIndex: 'time', key: 'time', width: 100 },
    { title: 'Event Description', dataIndex: 'description', key: 'description' },
  ];

  const highlightsColumns: ColumnsType<Highlight> = [
    { title: 'Start Time', dataIndex: 'start_time', key: 'start_time', width: 100 },
    { title: 'End Time', dataIndex: 'end_time', key: 'end_time', width: 100 },
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

          {/* Main Controls Card */}
          <Card style={{ marginBottom: 24, borderRadius: 8 }} bordered={false}>
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <div>
                <Text strong style={{ fontSize: 16, color: '#1e4d2b' }}>
                  Select a video to analyze
                </Text>
              </div>

              <Select
                placeholder={loading ? 'Loading videos...' : 'Select a video...'}
                style={{ width: '100%' }}
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

              <div>
                <Text strong style={{ display: 'block', marginBottom: 8, color: '#1e4d2b' }}>
                  Commentary Language
                </Text>
                <Radio.Group 
                  value={language} 
                  onChange={(e) => setLanguage(e.target.value)}
                  size="large"
                  buttonStyle="solid"
                  disabled={analyzing}
                  style={{ width: '100%' }}
                >
                  <Space size="large">
                    <Radio.Button value="English" style={{ minWidth: 120, textAlign: 'center' }}>English</Radio.Button>
                    <Radio.Button value="French" style={{ minWidth: 120, textAlign: 'center' }}>French</Radio.Button>
                    <Radio.Button value="Spanish" style={{ minWidth: 120, textAlign: 'center' }}>Spanish</Radio.Button>
                    <Radio.Button value="Swedish" style={{ minWidth: 120, textAlign: 'center' }}>Swedish</Radio.Button>
                    <Radio.Button value="Korean" style={{ minWidth: 120, textAlign: 'center' }}>Korean</Radio.Button>
                  </Space>
                </Radio.Group>
              </div>

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
                  width: '100%',
                  marginTop: 8
                }}
              >
                {analyzing ? 'Analyzing...' : `Analyze Video in ${language}`}
              </Button>

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
                  strokeColor={{ '0%': '#6fbf8b', '100%': '#1e4d2b' }}
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
                  <Text code>{generatedVideo.replace('/videos/generated/', 'videos/generated-videos/')}</Text>
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
                  🎬 Final Complete Video
                </Title>
              }
              style={{ borderRadius: 8, marginBottom: 24, border: '2px solid #6fbf8b' }}
            >
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <video
                  controls
                  style={{ width: '100%', maxWidth: '800px', borderRadius: 8 }}
                  src={`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'}${generatedVideo}`}
                >
                  Your browser does not support the video tag.
                </video>
              </div>
              <div style={{ marginTop: 16, textAlign: 'center' }}>
                <Text type="secondary">
                  Full concatenated video with all commentary segments
                </Text>
              </div>
            </Card>
          )}

          {/* Video Player - Show during streaming (chunk-by-chunk playback) */}
          {chunks.length > 0 && (
            <Card
              title={
                <Title level={4} style={{ margin: 0, color: '#1e4d2b' }}>
                  {isComplete ? '📺 Chunk Playback (Individual Segments)' : '🔴 Live Streaming Commentary'}
                </Title>
              }
              style={{ borderRadius: 8, marginBottom: 24 }}
            >
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <video
                  ref={videoRef}
                  controls
                  onEnded={handleVideoEnded}
                  style={{ width: '100%', maxWidth: '800px', borderRadius: 8 }}
                >
                  Your browser does not support the video tag.
                </video>
              </div>
            </Card>
          )}

          {highlights.length > 0 && !analyzing && (
            <Card
              title={
                <Title level={4} style={{ margin: 0, color: '#1e4d2b' }}>
                  Football Highlights & Events ({language})
                </Title>
              }
              style={{ borderRadius: 8, marginBottom: 24 }}
            >
              <div style={{ display: 'flex', gap: '16px' }}>
                <div style={{ flex: '0 0 45%' }}>
                  <Title level={5} style={{ color: '#1e4d2b', marginBottom: 12 }}>Detected Events</Title>
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
                  <Title level={5} style={{ color: '#1e4d2b', marginBottom: 12 }}>Generated Commentary</Title>
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

          {/* NEW SECTION: Feedback / Comments */}
          <Card
            title={
              <Title level={4} style={{ margin: 0, color: '#1e4d2b' }}>
                Feedback & Comments
              </Title>
            }
            style={{ borderRadius: 8, marginBottom: 24 }}
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              <Text>Have suggestions or found an issue? Let us know!</Text>
              <TextArea
                rows={4}
                value={userComment}
                onChange={(e) => setUserComment(e.target.value)}
                placeholder="Write your comments here..."
                maxLength={500}
                showCount
              />
              <div style={{ textAlign: 'right' }}>
                <Button 
                  type="primary" 
                  icon={<SendOutlined />} 
                  onClick={handleSubmitComment}
                  loading={submittingComment}
                  style={{ background: '#1e4d2b', borderColor: '#1e4d2b' }}
                >
                  Send Feedback
                </Button>
              </div>
            </Space>
          </Card>

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