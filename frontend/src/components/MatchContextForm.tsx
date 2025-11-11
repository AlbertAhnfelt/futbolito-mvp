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
  SearchOutlined,
  TrophyOutlined,
} from '@ant-design/icons';
import type { Player, MatchContext } from '../types';
import type { TeamDetails, GameDetails, RosterPlayer } from '../types/football';
import { matchContextApi } from '../services/api';
import { TeamSearchModal } from './TeamSearchModal';
import { GameSearchModal } from './GameSearchModal';
import { RosterPreview } from './RosterPreview';

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

  // Modal states
  const [homeTeamModalOpen, setHomeTeamModalOpen] = useState(false);
  const [awayTeamModalOpen, setAwayTeamModalOpen] = useState(false);
  const [gameModalOpen, setGameModalOpen] = useState(false);

  // Roster preview states
  const [homeRoster, setHomeRoster] = useState<RosterPlayer[] | null>(null);
  const [awayRoster, setAwayRoster] = useState<RosterPlayer[] | null>(null);

  useEffect(() => {
    loadContext();
  }, []);

  const loadContext = async () => {
    try {
      const context = await matchContextApi.getContext();
      if (context && context.teams.home.name) {
        form.setFieldsValue({
          homeTeamName: context.teams.home.name,
          awayTeamName: context.teams.away.name,
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
      position: '',
      notes: '',
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
            players: homePlayers.filter((p) => p.jersey && p.name),
          },
          away: {
            name: values.awayTeamName,
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
      setHomeRoster(null);
      setAwayRoster(null);
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

  const convertRosterToPlayers = (roster: RosterPlayer[]): Player[] => {
    return roster.map((player) => ({
      jersey: player.jersey_number || '',
      name: player.name,
      position: player.position || '',
      notes: player.nationality ? `${player.nationality}${player.age ? `, Age: ${player.age}` : ''}` : '',
    }));
  };

  const handleSelectHomeTeam = (team: TeamDetails) => {
    form.setFieldsValue({ homeTeamName: team.name });
    if (team.roster && team.roster.length > 0) {
      const players = convertRosterToPlayers(team.roster);
      setHomePlayers(players);
      setHomeRoster(team.roster);
      message.success(`Loaded ${team.roster.length} players for ${team.name}`);
    }
  };

  const handleSelectAwayTeam = (team: TeamDetails) => {
    form.setFieldsValue({ awayTeamName: team.name });
    if (team.roster && team.roster.length > 0) {
      const players = convertRosterToPlayers(team.roster);
      setAwayPlayers(players);
      setAwayRoster(team.roster);
      message.success(`Loaded ${team.roster.length} players for ${team.name}`);
    }
  };

  const handleSelectGame = (game: GameDetails) => {
    form.setFieldsValue({
      homeTeamName: game.home_team.name,
      awayTeamName: game.away_team.name,
    });

    if (game.home_lineup && game.home_lineup.length > 0) {
      const homePlayers = convertRosterToPlayers(game.home_lineup);
      setHomePlayers(homePlayers);
      setHomeRoster(game.home_lineup);
    }

    if (game.away_lineup && game.away_lineup.length > 0) {
      const awayPlayers = convertRosterToPlayers(game.away_lineup);
      setAwayPlayers(awayPlayers);
      setAwayRoster(game.away_lineup);
    }

    message.success(`Loaded game data for ${game.home_team.name} vs ${game.away_team.name}`);
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
            <Col span={4}>
              <Input
                placeholder="Jersey #"
                value={player.jersey}
                onChange={(e) =>
                  updatePlayer(team, index, 'jersey', e.target.value)
                }
                maxLength={3}
              />
            </Col>
            <Col span={8}>
              <Input
                placeholder="Player Name *"
                value={player.name}
                onChange={(e) =>
                  updatePlayer(team, index, 'name', e.target.value)
                }
              />
            </Col>
            <Col span={6}>
              <Input
                placeholder="Position"
                value={player.position}
                onChange={(e) =>
                  updatePlayer(team, index, 'position', e.target.value)
                }
              />
            </Col>
            <Col span={6}>
              <Input
                placeholder="Notes"
                value={player.notes}
                onChange={(e) =>
                  updatePlayer(team, index, 'notes', e.target.value)
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

            <Space style={{ width: '100%', justifyContent: 'center' }}>
              <Button
                type="primary"
                icon={<TrophyOutlined />}
                onClick={() => setGameModalOpen(true)}
                size="large"
                style={{
                  background: '#1890ff',
                  borderColor: '#1890ff',
                }}
              >
                Search Game (Quick Fill)
              </Button>
            </Space>

            <Divider>OR</Divider>

            <Form form={form} layout="vertical">
              <Row gutter={24}>
                <Col span={12}>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Form.Item
                      label={<Text strong>Home Team Name</Text>}
                      name="homeTeamName"
                      rules={[
                        { required: true, message: 'Please enter home team name' },
                      ]}
                      style={{ marginBottom: 8 }}
                    >
                      <Input
                        placeholder="e.g., Barcelona"
                        size="large"
                        style={{ borderColor: '#1e4d2b' }}
                      />
                    </Form.Item>
                    <Button
                      icon={<SearchOutlined />}
                      onClick={() => setHomeTeamModalOpen(true)}
                      block
                      style={{ marginBottom: 16 }}
                    >
                      Search Home Team
                    </Button>
                  </Space>

                  <Divider orientation="left">
                    <Text strong style={{ color: '#1e4d2b' }}>
                      Home Team Players
                    </Text>
                  </Divider>
                  {renderPlayerInputs(homePlayers, 'home', '#1e4d2b')}
                </Col>

                <Col span={12}>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Form.Item
                      label={<Text strong>Away Team Name</Text>}
                      name="awayTeamName"
                      rules={[
                        { required: true, message: 'Please enter away team name' },
                      ]}
                      style={{ marginBottom: 8 }}
                    >
                      <Input
                        placeholder="e.g., Real Madrid"
                        size="large"
                        style={{ borderColor: '#6fbf8b' }}
                      />
                    </Form.Item>
                    <Button
                      icon={<SearchOutlined />}
                      onClick={() => setAwayTeamModalOpen(true)}
                      block
                      style={{ marginBottom: 16 }}
                    >
                      Search Away Team
                    </Button>
                  </Space>

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

      {/* Search Modals */}
      <TeamSearchModal
        open={homeTeamModalOpen}
        onClose={() => setHomeTeamModalOpen(false)}
        onSelectTeam={handleSelectHomeTeam}
        title="Search Home Team"
      />

      <TeamSearchModal
        open={awayTeamModalOpen}
        onClose={() => setAwayTeamModalOpen(false)}
        onSelectTeam={handleSelectAwayTeam}
        title="Search Away Team"
      />

      <GameSearchModal
        open={gameModalOpen}
        onClose={() => setGameModalOpen(false)}
        onSelectGame={handleSelectGame}
      />

      {/* Roster Previews */}
      {homeRoster && (
        <RosterPreview
          teamName={form.getFieldValue('homeTeamName')}
          roster={homeRoster}
        />
      )}

      {awayRoster && (
        <RosterPreview
          teamName={form.getFieldValue('awayTeamName')}
          roster={awayRoster}
        />
      )}
    </Card>
  );
};
