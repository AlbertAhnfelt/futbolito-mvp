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
import type { Highlight } from './types';
import './App.css';

const { Header, Content, Footer } = Layout;
const { Title, Text } = Typography;

function App() {
  const [videos, setVideos] = useState<string[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<string>('');
  const [highlights, setHighlights] = useState<Highlight[]>([]);
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

    try {
      const results = await videoApi.analyzeVideo(selectedVideo);
      setHighlights(results);
    } catch (err: any) {
      const errorMessage =
        err.response?.data?.detail || err.message || 'Analysis failed';
      setError(`Error: ${errorMessage}`);
      console.error('Error analyzing video:', err);
    } finally {
      setAnalyzing(false);
    }
  };

  const columns: ColumnsType<Highlight> = [
    {
      title: 'Start Time',
      dataIndex: 'start_time',
      key: 'start_time',
      width: 120,
    },
    {
      title: 'End Time',
      dataIndex: 'end_time',
      key: 'end_time',
      width: 120,
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
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

          {highlights.length > 0 && !analyzing && (
            <Card
              title={
                <Title level={4} style={{ margin: 0, color: '#1e4d2b' }}>
                  Football Highlights
                </Title>
              }
              style={{ borderRadius: 8 }}
            >
              <Table
                columns={columns}
                dataSource={highlights}
                rowKey={(record, index) => `${record.start_time}-${index}`}
                pagination={{
                  pageSize: 10,
                  showSizeChanger: true,
                  showTotal: (total) => `Total ${total} highlights`,
                }}
              />
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
