import { useState, useEffect } from 'react';
import {
  Card,
  Form,
  Input,
  Button,
  Space,
  Divider,
  message,
  Collapse,
  Tag,
  Row,
  Col,
  Typography,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  SaveOutlined,
  ClearOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import type { Player, MatchContext } from '../types';
import { matchContextApi } from '../services/api';

const { Title, Text } = Typography;
const { Panel } = Collapse;

interface MatchContextFormProps {
  onContextSaved?: () => void;
}

export const MatchContextForm: React.FC<MatchContextFormProps> = ({
  onContextSaved,
}) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [hasContext, setHasContext] = useState(false);
  const [homePlayers, setHomePlayers] = useState<Player[]>([]);
  const [awayPlayers, setAwayPlayers] = useState<Player[]>([]);

  useEffect(() => {
    loadContext();
  }, []);

  const loadContext = async () => {
    try {
      const context = await matchContextApi.getContext();
      if (context && context.teams.home.name) {
        form.setFieldsValue({
          homeTeamName: context.teams.home.name,
          homeShirtColor: context.teams.home.shirt_color || '',
          awayTeamName: context.teams.away.name,
          awayShirtColor: context.teams.away.shirt_color || '',
        });
        setHomePlayers(context.teams.home.players || []);
        setAwayPlayers(context.teams.away.players || []);
        setHasContext(true);
      }
    } catch (error) {
      console.error('Error loading context:', error);
    }
  };

  const addPlayer = (team: 'home' | 'away') => {
    const newPlayer: Player = {
      jersey: '',
      name: '',
    };

    if (team === 'home') {
      setHomePlayers([...homePlayers, newPlayer]);
    } else {
      setAwayPlayers([...awayPlayers, newPlayer]);
    }
  };

  const removePlayer = (team: 'home' | 'away', index: number) => {
    if (team === 'home') {
      setHomePlayers(homePlayers.filter((_, i) => i !== index));
    } else {
      setAwayPlayers(awayPlayers.filter((_, i) => i !== index));
    }
  };

  const updatePlayer = (
    team: 'home' | 'away',
    index: number,
    field: keyof Player,
    value: string
  ) => {
    if (team === 'home') {
      const updated = [...homePlayers];
      updated[index] = { ...updated[index], [field]: value };
      setHomePlayers(updated);
    } else {
      const updated = [...awayPlayers];
      updated[index] = { ...updated[index], [field]: value };
      setAwayPlayers(updated);
    }
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      const context: MatchContext = {
        teams: {
          home: {
            name: values.homeTeamName,
            shirt_color: values.homeShirtColor || undefined,
            players: homePlayers.filter((p) => p.jersey && p.name),
          },
          away: {
            name: values.awayTeamName,
            shirt_color: values.awayShirtColor || undefined,
            players: awayPlayers.filter((p) => p.jersey && p.name),
          },
        },
      };

      await matchContextApi.saveContext(context);
      message.success('Match context saved successfully!');
      setHasContext(true);
      onContextSaved?.();
    } catch (error) {
      console.error('Error saving context:', error);
      message.error('Failed to save match context');
    } finally {
      setLoading(false);
    }
  };

  const handleClear = async () => {
    try {
      setLoading(true);
      await matchContextApi.clearContext();
      form.resetFields();
      setHomePlayers([]);
      setAwayPlayers([]);
      setHasContext(false);
      message.success('Match context cleared!');
      onContextSaved?.();
    } catch (error) {
      console.error('Error clearing context:', error);
      message.error('Failed to clear match context');
    } finally {
      setLoading(false);
    }
  };

  const renderPlayerInputs = (
    players: Player[],
    team: 'home' | 'away',
    teamColor: string
  ) => (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {players.map((player, index) => (
        <Card
          key={index}
          size="small"
          style={{ borderLeft: `3px solid ${teamColor}` }}
          extra={
            <Button
              type="text"
              danger
              size="small"
              icon={<DeleteOutlined />}
              onClick={() => removePlayer(team, index)}
            />
          }
        >
          <Row gutter={[8, 8]}>
            <Col span={6}>
              <Input
                placeholder="Jersey #"
                value={player.jersey}
                onChange={(e) =>
                  updatePlayer(team, index, 'jersey', e.target.value)
                }
                maxLength={3}
              />
            </Col>
            <Col span={18}>
              <Input
                placeholder="Player Name *"
                value={player.name}
                onChange={(e) =>
                  updatePlayer(team, index, 'name', e.target.value)
                }
              />
            </Col>
          </Row>
        </Card>
      ))}
      <Button
        type="dashed"
        onClick={() => addPlayer(team)}
        icon={<PlusOutlined />}
        style={{ width: '100%' }}
      >
        Add Player
      </Button>
    </Space>
  );

  return (
    <Card style={{ marginBottom: 24, borderRadius: 8 }} bordered={false}>
      <Collapse
        defaultActiveKey={hasContext ? [] : ['1']}
        style={{ background: 'transparent', border: 'none' }}
      >
        <Panel
          header={
            <Space>
              <TeamOutlined style={{ fontSize: 18, color: '#6fbf8b' }} />
              <Title level={5} style={{ margin: 0, color: '#1e4d2b' }}>
                Match Context (Optional - For Better Player Recognition)
              </Title>
              {hasContext && (
                <Tag color="success">Context Saved</Tag>
              )}
            </Space>
          }
          key="1"
        >
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Text type="secondary">
              Add team names and player information to help the AI recognize
              players by name instead of jersey numbers. This is especially
              useful for amateur matches where AI might not recognize players.
            </Text>

            <Form form={form} layout="vertical">
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item
                    label={<Text strong>Home Team Name</Text>}
                    name="homeTeamName"
                    rules={[
                      { required: true, message: 'Please enter home team name' },
                    ]}
                  >
                    <Input
                      placeholder="e.g., Barcelona"
                      size="large"
                      style={{ borderColor: '#1e4d2b' }}
                    />
                  </Form.Item>

                  <Form.Item
                    label={<Text strong>Home Team Shirt Color</Text>}
                    name="homeShirtColor"
                  >
                    <Input
                      placeholder="e.g., Red and Blue, White"
                      size="large"
                      style={{ borderColor: '#1e4d2b' }}
                    />
                  </Form.Item>

                  <Divider orientation="left">
                    <Text strong style={{ color: '#1e4d2b' }}>
                      Home Team Players
                    </Text>
                  </Divider>
                  {renderPlayerInputs(homePlayers, 'home', '#1e4d2b')}
                </Col>

                <Col span={12}>
                  <Form.Item
                    label={<Text strong>Away Team Name</Text>}
                    name="awayTeamName"
                    rules={[
                      { required: true, message: 'Please enter away team name' },
                    ]}
                  >
                    <Input
                      placeholder="e.g., Real Madrid"
                      size="large"
                      style={{ borderColor: '#6fbf8b' }}
                    />
                  </Form.Item>

                  <Form.Item
                    label={<Text strong>Away Team Shirt Color</Text>}
                    name="awayShirtColor"
                  >
                    <Input
                      placeholder="e.g., All White, Yellow and Green"
                      size="large"
                      style={{ borderColor: '#6fbf8b' }}
                    />
                  </Form.Item>

                  <Divider orientation="left">
                    <Text strong style={{ color: '#6fbf8b' }}>
                      Away Team Players
                    </Text>
                  </Divider>
                  {renderPlayerInputs(awayPlayers, 'away', '#6fbf8b')}
                </Col>
              </Row>
            </Form>

            <Divider />

            <Space>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSave}
                loading={loading}
                size="large"
                style={{
                  background: '#6fbf8b',
                  borderColor: '#6fbf8b',
                }}
              >
                Save Match Context
              </Button>
              <Button
                danger
                icon={<ClearOutlined />}
                onClick={handleClear}
                loading={loading}
                size="large"
              >
                Clear Context
              </Button>
            </Space>
          </Space>
        </Panel>
      </Collapse>
    </Card>
  );
};
