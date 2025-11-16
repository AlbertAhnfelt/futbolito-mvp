import { useState, useEffect } from 'react';
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
} from 'antd';
import { PlayCircleOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { videoApi } from './services/api';
import type { Highlight, Event } from './types';
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

  const handleAnalyze = async () => {
    if (!selectedVideo) {
      setError('Please select a video');
      return;
    }

    setAnalyzing(true);
    setError('');
    setHighlights([]);
    setEvents([]);
    setGeneratedVideo('');

    try {
      const results = await videoApi.analyzeVideo(selectedVideo);
      setHighlights(results.highlights);
      setGeneratedVideo(results.generated_video);

      // Fetch events
      try {
        const eventsData = await videoApi.getEvents();
        setEvents(eventsData.events || []);
      } catch (eventsErr) {
        console.warn('Could not load events:', eventsErr);
        // Don't fail the entire analysis if events can't be loaded
      }
    } catch (err: any) {
      const errorMessage =
        err.response?.data?.detail || err.message || 'Analysis failed';
      setError(`Error: ${errorMessage}`);
      console.error('Error analyzing video:', err);
    } finally {
      setAnalyzing(false);
    }
  };

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
            <Card style={{ textAlign: 'center', marginBottom: 24 }}>
              <Spin size="large" />
              <div style={{ marginTop: 16, color: '#5aa876' }}>
                <Text>Analyzing video with AI... This may take a minute.</Text>
              </div>
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

          {highlights.length > 0 && !analyzing && (
            <>
              <Card
                title={
                  <Title level={4} style={{ margin: 0, color: '#1e4d2b' }}>
                    Football Highlights & Events
                  </Title>
                }
                style={{ borderRadius: 8, marginBottom: 24 }}
              >
                <div style={{ display: 'flex', gap: '16px' }}>
                  {/* Left Table - Events */}
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

                  {/* Right Table - Highlights */}
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

              {generatedVideo && (
                <Card
                  title={
                    <Title level={4} style={{ margin: 0, color: '#1e4d2b' }}>
                      Generated Commentary Video
                    </Title>
                  }
                  style={{ borderRadius: 8 }}
                >
                  <div style={{ display: 'flex', justifyContent: 'center' }}>
                    <video
                      controls
                      style={{ width: '100%', maxWidth: '800px', borderRadius: 8 }}
                      src={`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'}/videos/generated/${generatedVideo}`}
                    >
                      Your browser does not support the video tag.
                    </video>
                  </div>
                </Card>
              )}
            </>
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
